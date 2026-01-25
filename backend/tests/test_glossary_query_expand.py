from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.glossary_term import GlossaryTerm
from app.models.worldbook_entry import WorldBookEntry
from app.services.worldbook_service import preview_worldbook_trigger


class TestGlossaryQueryExpand(unittest.TestCase):
    def _make_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO projects (id) VALUES ('project-1')")
        WorldBookEntry.__table__.create(engine)
        GlossaryTerm.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return SessionLocal

    def test_worldbook_trigger_can_expand_query_by_glossary_alias(self) -> None:
        SessionLocal = self._make_db()
        now = datetime.now(timezone.utc)

        orig = getattr(settings, "glossary_query_expand_enabled", False)
        try:
            with SessionLocal() as db:
                db.add(
                    WorldBookEntry(
                        id="WB1",
                        project_id="project-1",
                        title="Alpha",
                        content_md="Alpha content",
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(["alpha"]),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=9999,
                        priority="important",
                        updated_at=now,
                    )
                )
                db.add(
                    GlossaryTerm(
                        id="G1",
                        project_id="project-1",
                        term="alpha",
                        aliases_json=json.dumps(["beta"], ensure_ascii=False),
                        sources_json="[]",
                        origin="manual",
                        enabled=1,
                    )
                )
                db.commit()

                settings.glossary_query_expand_enabled = False
                out_disabled = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="beta",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )
                self.assertEqual([t.id for t in out_disabled.triggered], [])

                settings.glossary_query_expand_enabled = True
                out_enabled = preview_worldbook_trigger(
                    db=db,
                    project_id="project-1",
                    query_text="beta",
                    include_constant=False,
                    enable_recursion=False,
                    char_limit=200000,
                )
        finally:
            settings.glossary_query_expand_enabled = orig

        reason_by_id = {t.id: t.reason for t in out_enabled.triggered}
        self.assertEqual(reason_by_id.get("WB1"), "keyword:alpha")

