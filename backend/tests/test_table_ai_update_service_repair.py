from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.chapter import Chapter
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_table import ProjectTable
from app.models.project_table import ProjectTableRow
from app.models.user import User
from app.services.generation_service import RecordedLlmResult
from app.services.table_ai_update_service import table_ai_update_v1


def _compact_json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TestTableAiUpdateServiceRepair(unittest.TestCase):
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
                ProjectTable.__table__,
                ProjectTableRow.__table__,
                LLMPreset.__table__,
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
                    content_md="Alice earns 10 gold.",
                    summary=None,
                    status="done",
                )
            )
            db.add(
                ProjectTable(
                    id="t1",
                    project_id="p1",
                    table_key="money",
                    name="Money",
                    schema_version=1,
                    schema_json='{"version":1,"columns":[{"key":"key","type":"string","required":true},{"key":"value","type":"number","required":true}]}',
                )
            )
            db.add(LLMPreset(project_id="p1", provider="openai", base_url=None, model="gpt-test"))
            db.commit()

    def test_table_ai_update_repairs_parse_failed_once(self) -> None:
        repaired_value = {
            "title": "Table Update",
            "summary_md": "auto",
            "ops": [
                {
                    "op": "upsert",
                    "table_id": "t1",
                    "row_index": 0,
                    "data": {"key": "gold", "value": 10},
                }
            ],
        }

        with patch("app.services.table_ai_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.table_ai_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.table_ai_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text="not json",
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-orig",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-orig"}],
            ),
        ), patch(
            "app.services.table_ai_update_service.repair_json_once",
            return_value={
                "ok": True,
                "repair_run_id": "run-repair",
                "value": repaired_value,
                "raw_json": _compact_json_dumps(repaired_value),
                "finish_reason": "stop",
                "warnings": [],
            },
        ), patch(
            "app.services.table_ai_update_service.propose_project_table_change_set",
            return_value={"change_set_id": "cs1"},
        ):
            res = table_ai_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                table_id="t1",
                change_set_idempotency_key="tblupd-12345678",
                chapter_id="c1",
                focus=None,
            )

        self.assertTrue(bool(res.get("ok")))
        self.assertEqual(res.get("run_id"), "run-orig")
        self.assertEqual(res.get("repair_run_id"), "run-repair")
