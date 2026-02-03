from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.generation_run import GenerationRun
from app.services import table_ai_update_service


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

