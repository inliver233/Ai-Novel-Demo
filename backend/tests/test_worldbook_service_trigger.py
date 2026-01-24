from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.worldbook_entry import WorldBookEntry
from app.services.worldbook_service import preview_worldbook_trigger


class TestWorldBookServiceTrigger(unittest.TestCase):
    def _make_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
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

    def test_preview_trigger_keyword_boundary_option(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        with SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id="S1",
                        project_id="project-1",
                        title="substring",
                        content_md="S1 content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["he"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                    WorldBookEntry(
                        id="W1",
                        project_id="project-1",
                        title="word_boundary",
                        content_md="W1 content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["word:he"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    ),
                ]
            )
            db.commit()

            out_substring = preview_worldbook_trigger(
                db=db,
                project_id="project-1",
                query_text="the",
                include_constant=False,
                enable_recursion=False,
                char_limit=200000,
            )
            out_word = preview_worldbook_trigger(
                db=db,
                project_id="project-1",
                query_text="he",
                include_constant=False,
                enable_recursion=False,
                char_limit=200000,
            )

        ids_substring = {t.id for t in out_substring.triggered}
        self.assertIn("S1", ids_substring)
        self.assertNotIn("W1", ids_substring)

        ids_word = {t.id for t in out_word.triggered}
        self.assertIn("S1", ids_word)
        self.assertIn("W1", ids_word)

    def test_preview_trigger_alias_matching_feature_flag(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        orig_alias_enabled = getattr(settings, "worldbook_match_alias_enabled", False)
        try:
            with SessionLocal() as db:
                db.add(
                    WorldBookEntry(
                        id="A",
                        project_id="project-1",
                        title="Alias Entry",
                        content_md="Alias content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["alpha|beta"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    )
                )
                db.commit()

                settings.worldbook_match_alias_enabled = False
                out_disabled = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="beta",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )
                self.assertEqual([t.id for t in out_disabled.triggered], [])

                settings.worldbook_match_alias_enabled = True
                out_enabled = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="beta",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )

            reason_by_id = {t.id: t.reason for t in out_enabled.triggered}
            self.assertEqual(reason_by_id.get("A"), "alias:beta")
        finally:
            settings.worldbook_match_alias_enabled = orig_alias_enabled

    def test_preview_trigger_regex_allowlist(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        orig_enabled = getattr(settings, "worldbook_match_regex_enabled", False)
        orig_allowlist = getattr(settings, "worldbook_match_regex_allowlist_json", None)
        try:
            with SessionLocal() as db:
                db.add(
                    WorldBookEntry(
                        id="R1",
                        project_id="project-1",
                        title="Regex Entry",
                        content_md="Regex content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps([r"re:dragon\d+"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    )
                )
                db.commit()

                settings.worldbook_match_regex_enabled = True
                settings.worldbook_match_regex_allowlist_json = json.dumps([])
                out_blocked = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="dragon12",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )
                self.assertEqual([t.id for t in out_blocked.triggered], [])

                settings.worldbook_match_regex_allowlist_json = json.dumps([r"dragon\d+"])
                out_allowed = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="dragon12",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )

            reason_by_id = {t.id: t.reason for t in out_allowed.triggered}
            self.assertEqual(reason_by_id.get("R1"), r"regex:dragon\d+")
        finally:
            settings.worldbook_match_regex_enabled = orig_enabled
            settings.worldbook_match_regex_allowlist_json = orig_allowlist

    def test_preview_trigger_pinyin_matching_optional_dependency(self) -> None:
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=DeprecationWarning,
                    message=r".*codecs\.open\(\) is deprecated.*",
                )
                import pypinyin  # noqa: F401  # type: ignore[import-not-found]
        except Exception:
            self.skipTest("pypinyin not installed")

        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        orig_enabled = getattr(settings, "worldbook_match_pinyin_enabled", False)
        try:
            with SessionLocal() as db:
                db.add(
                    WorldBookEntry(
                        id="P1",
                        project_id="project-1",
                        title="Pinyin Entry",
                        content_md="Pinyin content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["世界书"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    )
                )
                db.commit()

                settings.worldbook_match_pinyin_enabled = True
                out = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="sjs",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )

            reason_by_id = {t.id: t.reason for t in out.triggered}
            self.assertEqual(reason_by_id.get("P1"), "pinyin:世界书")
        finally:
            settings.worldbook_match_pinyin_enabled = orig_enabled
