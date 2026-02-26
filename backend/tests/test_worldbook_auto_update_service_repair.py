from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.core.errors import AppError
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
        output_with_item = _compact_json_dumps(
            {
                "schema_version": "worldbook_auto_update_v1",
                "title": "bad",
                "summary_md": "",
                "ops": [{"op": "create", "item": {"title": "Town", "content": "desc", "priority": 1}}],
            }
        )

        with patch("app.services.worldbook_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.worldbook_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.llm_retry.call_llm_and_record",
            return_value=RecordedLlmResult(
                text=output_with_item,
                finish_reason=None,
                latency_ms=1,
                dropped_params=[],
                run_id="run-orig",
            ),
        ), patch("app.services.worldbook_auto_update_service.repair_json_once") as mock_repair, patch(
            "app.services.worldbook_auto_update_service.schedule_search_rebuild_task", return_value=None
        ), patch(
            "app.services.worldbook_auto_update_service.schedule_vector_rebuild_task", return_value=None
        ):
            res = worldbook_auto_update_v1(project_id="p1", actor_user_id="u1", request_id="rid-test", chapter_id="c1")

        self.assertTrue(bool(res.get("ok")))
        self.assertEqual(res.get("run_id"), "run-orig")
        self.assertIsNone(res.get("repair_run_id"))
        mock_repair.assert_not_called()

        with self.SessionLocal() as db:
            rows = (
                db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == "p1").order_by(WorldBookEntry.title.asc()))
                .scalars()
                .all()
            )
            self.assertEqual([r.title for r in rows], ["Town"])

    def test_worldbook_auto_update_retries_once_on_timeout_and_succeeds(self) -> None:
        model_out = _compact_json_dumps(
            {
                "schema_version": "worldbook_auto_update_v1",
                "title": None,
                "summary_md": None,
                "ops": [
                    {
                        "op": "create",
                        "entry": {
                            "title": "Town",
                            "content_md": "desc",
                            "keywords": [],
                            "aliases": [],
                            "enabled": True,
                            "constant": False,
                            "exclude_recursion": False,
                            "prevent_recursion": False,
                            "char_limit": 12000,
                            "priority": "optional",
                        },
                        "reason": "chapter mentions town",
                    }
                ],
            }
        )

        timeout_exc = AppError(code="LLM_TIMEOUT", message="timeout", status_code=504, details={"run_id": "run-orig"})
        ok = RecordedLlmResult(text=model_out, finish_reason=None, latency_ms=1, dropped_params=[], run_id="run-retry")

        with patch.dict(
            os.environ,
            {"TASK_LLM_MAX_ATTEMPTS": "2", "TASK_LLM_RETRY_BASE_SECONDS": "0", "TASK_LLM_RETRY_JITTER": "0"},
            clear=False,
        ), patch("app.services.worldbook_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.worldbook_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.llm_retry.call_llm_and_record",
            side_effect=[timeout_exc, ok],
        ) as mock_call, patch("app.services.worldbook_auto_update_service.schedule_search_rebuild_task", return_value=None), patch(
            "app.services.worldbook_auto_update_service.schedule_vector_rebuild_task", return_value=None
        ):
            res = worldbook_auto_update_v1(project_id="p1", actor_user_id="u1", request_id="rid-test", chapter_id="c1")

        self.assertTrue(bool(res.get("ok")))
        self.assertEqual(res.get("run_id"), "run-retry")
        self.assertIn("llm_retry_used", list(res.get("warnings") or []))
        self.assertEqual(mock_call.call_count, 2)
        self.assertTrue(str(mock_call.call_args_list[1].kwargs.get("request_id") or "").endswith(":retry1"))
