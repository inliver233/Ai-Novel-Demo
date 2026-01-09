from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.worldbook_entry import WorldBookEntry
from app.services.worldbook_service import preview_worldbook_trigger


class TestWorldBookServiceTrigger(unittest.TestCase):
    def _make_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO projects (id) VALUES ('project-1')")
        WorldBookEntry.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return SessionLocal

    def test_preview_trigger_recursion_and_controls(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        with SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id="A",
                        project_id="project-1",
                        title="A",
                        content_md="Alpha mentions beta and gamma.",
                        enabled=True,
                        constant=True,
                        keywords_json="[]",
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                    WorldBookEntry(
                        id="B",
                        project_id="project-1",
                        title="B",
                        content_md="B content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["beta"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                    # exclude_recursion=true means it only checks query_text (not recursion text).
                    WorldBookEntry(
                        id="C",
                        project_id="project-1",
                        title="C",
                        content_md="C content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["gamma"]),
                        exclude_recursion=True,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                    # prevent_recursion=true means its content won't be used to trigger others.
                    WorldBookEntry(
                        id="D",
                        project_id="project-1",
                        title="D",
                        content_md="Delta keyword should NOT trigger others.",
                        enabled=True,
                        constant=True,
                        keywords_json="[]",
                        exclude_recursion=False,
                        prevent_recursion=True,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                    WorldBookEntry(
                        id="E",
                        project_id="project-1",
                        title="E",
                        content_md="E content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["delta"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                ]
            )
            db.commit()

            out = preview_worldbook_trigger(
                db=db,
                project_id="project-1",
                query_text="",
                include_constant=True,
                enable_recursion=True,
                char_limit=200000,
            )

        reason_by_id = {t.id: t.reason for t in out.triggered}
        self.assertEqual(reason_by_id.get("A"), "constant")
        self.assertEqual(reason_by_id.get("D"), "constant")
        self.assertEqual(reason_by_id.get("B"), "keyword:beta")
        self.assertNotIn("C", reason_by_id)
        self.assertNotIn("E", reason_by_id)

        self.assertIn("<WORLD_BOOK>", out.text_md)
        self.assertIn("【世界书条目：A", out.text_md)
        self.assertIn("【世界书条目：B", out.text_md)
        self.assertNotIn("【世界书条目：C", out.text_md)
        self.assertNotIn("【世界书条目：E", out.text_md)

    def test_preview_trigger_disable_recursion(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        with SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id="A",
                        project_id="project-1",
                        title="A",
                        content_md="Alpha mentions beta.",
                        enabled=True,
                        constant=True,
                        keywords_json="[]",
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                    WorldBookEntry(
                        id="B",
                        project_id="project-1",
                        title="B",
                        content_md="B content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["beta"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                ]
            )
            db.commit()

            out = preview_worldbook_trigger(
                db=db,
                project_id="project-1",
                query_text="",
                include_constant=True,
                enable_recursion=False,
                char_limit=200000,
            )

        reason_by_id = {t.id: t.reason for t in out.triggered}
        self.assertEqual(reason_by_id.get("A"), "constant")
        self.assertNotIn("B", reason_by_id)

    def test_preview_trigger_char_limit_truncation(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        with SessionLocal() as db:
            db.add(
                WorldBookEntry(
                    id="A",
                    project_id="project-1",
                    title="A",
                    content_md="X" * 1000,
                    enabled=True,
                    constant=True,
                    keywords_json="[]",
                    exclude_recursion=False,
                    prevent_recursion=False,
                    char_limit=1000,
                    priority="important",
                    updated_at=now,
                )
            )
            db.commit()

            out = preview_worldbook_trigger(
                db=db,
                project_id="project-1",
                query_text="",
                include_constant=True,
                enable_recursion=True,
                char_limit=200,
            )

        self.assertTrue(out.truncated)
        self.assertIn("<WORLD_BOOK>", out.text_md)
        self.assertIn("</WORLD_BOOK>", out.text_md)
