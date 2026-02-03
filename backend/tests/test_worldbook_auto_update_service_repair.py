from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.chapter import Chapter
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.models.user import User
from app.models.worldbook_entry import WorldBookEntry
from app.services.generation_service import RecordedLlmResult
from app.services.worldbook_auto_update_service import worldbook_auto_update_v1


def _compact_json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TestWorldbookAutoUpdateServiceRepair(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)

        Base.metadata.create_all(
            engine,
            tables=[
                User.__table__,
                Project.__table__,
                Outline.__table__,
                Chapter.__table__,
                LLMPreset.__table__,
                ProjectSettings.__table__,
                WorldBookEntry.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="P1", genre=None, logline=None))
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md="outline", structure_json=None))
            db.add(
                Chapter(
                    id="c1",
                    project_id="p1",
                    outline_id="o1",
                    number=1,
                    title="Ch1",
                    plan=None,
                    content_md="Alice meets Bob.",
                    summary="summary",
                    status="done",
                )
            )
            db.add(LLMPreset(project_id="p1", provider="openai", base_url=None, model="gpt-test"))
            db.add(ProjectSettings(project_id="p1"))
            db.commit()

    def test_worldbook_auto_update_repairs_schema_drift_once(self) -> None:
        invalid = _compact_json_dumps(
            {
                "schema_version": "worldbook_auto_update_v1",
                "title": "bad",
                "summary_md": "",
                "ops": [{"op": "create", "item": {"title": "Town", "content": "desc", "priority": 1}}],
            }
        )
        repaired_value = {
            "schema_version": "worldbook_auto_update_v1",
            "title": "Worldbook Auto Update",
            "summary_md": "auto",
            "ops": [{"op": "create", "entry": {"title": "Town", "content_md": "desc", "keywords": [], "aliases": []}}],
        }

        with patch("app.services.worldbook_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.worldbook_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.worldbook_auto_update_service.call_llm_and_record",
            return_value=RecordedLlmResult(
                text=invalid,
                finish_reason=None,
                latency_ms=1,
                dropped_params=[],
                run_id="run-orig",
            ),
        ), patch(
            "app.services.worldbook_auto_update_service.repair_json_once",
            return_value={
                "ok": True,
                "repair_run_id": "run-repair",
                "value": repaired_value,
                "raw_json": _compact_json_dumps(repaired_value),
                "finish_reason": "stop",
                "warnings": [],
            },
        ), patch("app.services.worldbook_auto_update_service.schedule_search_rebuild_task", return_value=None), patch(
            "app.services.worldbook_auto_update_service.schedule_vector_rebuild_task", return_value=None
        ):
            res = worldbook_auto_update_v1(project_id="p1", actor_user_id="u1", request_id="rid-test", chapter_id="c1")

        self.assertTrue(bool(res.get("ok")))
        self.assertEqual(res.get("run_id"), "run-orig")
        self.assertEqual(res.get("repair_run_id"), "run-repair")

        with self.SessionLocal() as db:
            rows = (
                db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == "p1").order_by(WorldBookEntry.title.asc()))
                .scalars()
                .all()
            )
            self.assertEqual([r.title for r in rows], ["Town"])

