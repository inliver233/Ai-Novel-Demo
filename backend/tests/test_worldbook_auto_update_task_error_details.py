from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.services import project_task_service


class TestWorldbookAutoUpdateTaskErrorDetails(unittest.TestCase):
    def test_failed_worldbook_auto_update_records_reason_and_how_to_fix(self) -> None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)

        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")

        ProjectTask.__table__.create(engine)
        ProjectTaskEvent.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with SessionLocal() as db:
            db.add(
                ProjectTask(
                    id="pt-wb",
                    project_id="p1",
                    actor_user_id="u1",
                    kind="worldbook_auto_update",
                    status="queued",
                    idempotency_key="worldbook:chapter:c1:since:t:v1",
                    params_json=json.dumps({"chapter_id": "c1"}, ensure_ascii=False),
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        failure = {
            "ok": False,
            "project_id": "p1",
            "reason": "llm_call_failed",
            "run_id": "run-1",
            "error_type": "HTTPStatusError",
            "error_message": "boom",
            "attempts": [{"attempt": 1, "request_id": "rid-test", "run_id": "run-1", "error_code": "LLM_TIMEOUT"}],
            "error": {"code": "LLM_TIMEOUT", "details": {"attempts": [{"attempt": 1, "request_id": "rid-test"}]}},
        }

        with patch.object(project_task_service, "SessionLocal", SessionLocal):
            with patch("app.services.worldbook_auto_update_service.worldbook_auto_update_v1", return_value=failure):
                project_task_service.run_project_task(task_id="pt-wb")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-wb")
            self.assertIsNotNone(task)
            assert task is not None

            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("error_type"), "AppError")
            self.assertEqual(err.get("code"), "WORLDBOOK_AUTO_UPDATE_FAILED")
            msg = str(err.get("message") or "")
            self.assertIn("worldbook_auto_update", msg)
            self.assertIn("llm_call_failed", msg)

            details = err.get("details") or {}
            self.assertEqual(details.get("reason"), "llm_call_failed")
            self.assertEqual(details.get("run_id"), "run-1")
            self.assertEqual(details.get("error_type"), "HTTPStatusError")
            self.assertEqual(details.get("error_message"), "boom")
            self.assertIsInstance(details.get("attempts"), list)
            self.assertGreaterEqual(len(details.get("attempts") or []), 1)

            how = details.get("how_to_fix") or []
            self.assertIsInstance(how, list)
            self.assertGreater(len(how), 0)

    def test_missing_actor_user_id_records_config_error(self) -> None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)

        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")

        ProjectTask.__table__.create(engine)
        ProjectTaskEvent.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with SessionLocal() as db:
            db.add(
                ProjectTask(
                    id="pt-wb-missing-actor",
                    project_id="p1",
                    actor_user_id=None,
                    kind="worldbook_auto_update",
                    status="queued",
                    idempotency_key="worldbook:project:since:t:v1",
                    params_json=json.dumps({"chapter_id": "c1"}, ensure_ascii=False),
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        with patch.object(project_task_service, "SessionLocal", SessionLocal):
            project_task_service.run_project_task(task_id="pt-wb-missing-actor")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-wb-missing-actor")
            self.assertIsNotNone(task)
            assert task is not None

            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("error_type"), "AppError")
            self.assertEqual(err.get("code"), "PROJECT_TASK_CONFIG_ERROR")
            msg = str(err.get("message") or "")
            self.assertIn("actor_user_id", msg)
