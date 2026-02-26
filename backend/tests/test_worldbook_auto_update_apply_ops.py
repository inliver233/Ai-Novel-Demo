from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry
from app.services.worldbook_auto_update_service import apply_worldbook_auto_update_ops


class TestWorldbookAutoUpdateApplyOps(unittest.TestCase):
    def _make_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO projects (id) VALUES ('project-1')")
        ProjectSettings.__table__.create(engine)
        WorldBookEntry.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return SessionLocal

    def test_create_on_existing_does_not_override_metadata(self) -> None:
        SessionLocal = self._make_db()

        with SessionLocal() as db:
            db.add(
                WorldBookEntry(
                    id="E1",
                    project_id="project-1",
                    title="Dragon",
                    content_md="Old content.",
                    enabled=False,
                    constant=True,
                    keywords_json=json.dumps(["Dragon", "alias:Drake"], ensure_ascii=False),
                    exclude_recursion=False,
                    prevent_recursion=False,
                    char_limit=123,
                    priority="important",
                )
            )
            db.commit()

            with patch("app.services.worldbook_auto_update_service.schedule_vector_rebuild_task"), patch(
                "app.services.worldbook_auto_update_service.schedule_search_rebuild_task"
            ):
                out = apply_worldbook_auto_update_ops(
                    db=db,
                    project_id="project-1",
                    ops=[
                        {
                            "op": "create",
                            "entry": {
                                "title": "Dragon",
                                "content_md": "New content.",
                                "keywords": ["wyrm"],
                                "aliases": ["drake"],
                                "enabled": True,
                                "constant": False,
                                "exclude_recursion": False,
                                "prevent_recursion": False,
                                "char_limit": 999,
                                "priority": "critical",
                            },
                        }
                    ],
                )

            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("created"), 0)
            self.assertEqual(out.get("updated"), 1)

            row = db.get(WorldBookEntry, "E1")
            assert row is not None
            self.assertEqual(row.content_md, "Old content.")
            self.assertFalse(row.enabled)
            self.assertTrue(row.constant)
            self.assertEqual(row.char_limit, 123)
            self.assertEqual(row.priority, "important")
            self.assertIn("wyrm", json.loads(row.keywords_json or "[]"))
            self.assertIn("drake", json.loads(row.keywords_json or "[]"))

    def test_update_empty_content_does_not_wipe(self) -> None:
        SessionLocal = self._make_db()

        with SessionLocal() as db:
            db.add(
                WorldBookEntry(
                    id="E1",
                    project_id="project-1",
                    title="Dragon",
                    content_md="Old content.",
                    enabled=True,
                    constant=False,
                    keywords_json="[]",
                    exclude_recursion=False,
                    prevent_recursion=False,
                    char_limit=12000,
                    priority="important",
                )
            )
            db.commit()

            with patch("app.services.worldbook_auto_update_service.schedule_vector_rebuild_task"), patch(
                "app.services.worldbook_auto_update_service.schedule_search_rebuild_task"
            ):
                out = apply_worldbook_auto_update_ops(
                    db=db,
                    project_id="project-1",
                    ops=[{"op": "update", "match_title": "Dragon", "entry": {"content_md": ""}}],
                )

            self.assertTrue(out.get("ok"))
            row = db.get(WorldBookEntry, "E1")
            assert row is not None
            self.assertEqual(row.content_md, "Old content.")

    def test_update_short_content_appends_instead_of_replace(self) -> None:
        SessionLocal = self._make_db()

        with SessionLocal() as db:
            db.add(
                WorldBookEntry(
                    id="E1",
                    project_id="project-1",
                    title="Dragon",
                    content_md="A" * 100,
                    enabled=True,
                    constant=False,
                    keywords_json="[]",
                    exclude_recursion=False,
                    prevent_recursion=False,
                    char_limit=12000,
                    priority="important",
                )
            )
            db.commit()

            with patch("app.services.worldbook_auto_update_service.schedule_vector_rebuild_task"), patch(
                "app.services.worldbook_auto_update_service.schedule_search_rebuild_task"
            ):
                out = apply_worldbook_auto_update_ops(
                    db=db,
                    project_id="project-1",
                    ops=[{"op": "update", "match_title": "Dragon", "entry": {"content_md": "B" * 10}}],
                )

            self.assertTrue(out.get("ok"))
            row = db.get(WorldBookEntry, "E1")
            assert row is not None
            self.assertIn("A" * 100, row.content_md)
            self.assertIn("---", row.content_md)
            self.assertIn("B" * 10, row.content_md)

    def test_dedupe_merges_content_and_deletes_duplicates(self) -> None:
        SessionLocal = self._make_db()

        with SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id="A",
                        project_id="project-1",
                        title="A",
                        content_md="Alpha",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["A"], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority="important",
                    ),
                    WorldBookEntry(
                        id="B",
                        project_id="project-1",
                        title="B",
                        content_md="Beta",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["B"], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority="important",
                    ),
                ]
            )
            db.commit()

            with patch("app.services.worldbook_auto_update_service.schedule_vector_rebuild_task"), patch(
                "app.services.worldbook_auto_update_service.schedule_search_rebuild_task"
            ):
                out = apply_worldbook_auto_update_ops(
                    db=db,
                    project_id="project-1",
                    ops=[{"op": "dedupe", "canonical_title": "A", "duplicate_titles": ["B"]}],
                )

            self.assertTrue(out.get("ok"))
            self.assertEqual(out.get("deleted"), 1)

            canon = db.get(WorldBookEntry, "A")
            assert canon is not None
            self.assertIn("Alpha", canon.content_md)
            self.assertIn("---", canon.content_md)
            self.assertIn("Beta", canon.content_md)
            self.assertEqual(set(json.loads(canon.keywords_json or "[]")), {"A", "B"})
            self.assertIsNone(db.get(WorldBookEntry, "B"))

            # sanity: project_settings marked dirty
            settings = db.get(ProjectSettings, "project-1")
            assert settings is not None
            self.assertTrue(settings.vector_index_dirty)

            # no silent duplicates
            titles = db.execute(select(WorldBookEntry.title)).scalars().all()
            self.assertEqual(sorted(titles), ["A"])

    def test_noop_ops_does_not_schedule_rebuild_or_mark_dirty(self) -> None:
        SessionLocal = self._make_db()

        with SessionLocal() as db:
            with patch("app.services.worldbook_auto_update_service.schedule_vector_rebuild_task") as mock_vector, patch(
                "app.services.worldbook_auto_update_service.schedule_search_rebuild_task"
            ) as mock_search:
                out = apply_worldbook_auto_update_ops(db=db, project_id="project-1", ops=[])

            self.assertTrue(out.get("ok"))
            self.assertTrue(out.get("no_op"))
            self.assertEqual(out.get("created"), 0)
            self.assertEqual(out.get("updated"), 0)
            self.assertEqual(out.get("deleted"), 0)
            mock_vector.assert_not_called()
            mock_search.assert_not_called()

            settings = db.get(ProjectSettings, "project-1")
            self.assertIsNone(settings)
