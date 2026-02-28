from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.user import User
from app.services import table_ai_update_service
from app.services.llm_retry import LlmRetryExhausted
from app.services.table_ai_update_service import table_ai_update_v1


class TestTableAiUpdateLlmErrorRunId(unittest.TestCase):
    def test_llm_call_failed_can_resolve_run_id_by_request_id(self) -> None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)

        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE chapters (id VARCHAR(36) PRIMARY KEY)")

        GenerationRun.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with SessionLocal() as db:
            db.add(
                GenerationRun(
                    id="run-test",
                    project_id="p1",
                    actor_user_id=None,
                    chapter_id=None,
                    type="table_ai_update_auto_propose",
                    provider=None,
                    model=None,
                    request_id="rid-test",
                    prompt_system="",
                    prompt_user="",
                    prompt_render_log_json=None,
                    params_json="{}",
                    output_text=None,
                    error_json="{}",
                )
            )
            db.commit()

        with patch.object(table_ai_update_service, "SessionLocal", SessionLocal):
            run_id = table_ai_update_service._find_latest_run_id_for_request(
                project_id="p1", request_id="rid-test", run_type="table_ai_update_auto_propose"
            )

        self.assertEqual(run_id, "run-test")

    def test_table_ai_update_v1_llm_call_failed_returns_run_id_when_generation_run_exists(self) -> None:
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
                GenerationRun.__table__,
            ],
        )
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with SessionLocal() as db:
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
            db.add(
                GenerationRun(
                    id="run-test",
                    project_id="p1",
                    actor_user_id=None,
                    chapter_id=None,
                    type="table_ai_update_auto_propose",
                    provider=None,
                    model=None,
                    request_id="rid-test",
                    prompt_system="",
                    prompt_user="",
                    prompt_render_log_json=None,
                    params_json="{}",
                    output_text=None,
                    error_json="{}",
                )
            )
            db.commit()

        with patch.object(table_ai_update_service, "SessionLocal", SessionLocal), patch(
            "app.services.table_ai_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.table_ai_update_service.call_llm_and_record_with_retries",
            side_effect=LlmRetryExhausted(
                error_type="TimeoutError",
                error_message="timeout",
                error_code=None,
                status_code=None,
                run_id=None,
                attempts=[{"attempt": 1, "request_id": "rid-test", "run_id": None}],
                last_exception=TimeoutError("timeout"),
            ),
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

        self.assertFalse(bool(res.get("ok")))
        self.assertEqual(res.get("reason"), "llm_call_failed")
        self.assertEqual(res.get("run_id"), "run-test")
