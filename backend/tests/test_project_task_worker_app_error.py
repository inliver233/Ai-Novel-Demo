from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.services import project_task_service


class TestProjectTaskWorkerAppError(unittest.TestCase):
    def test_app_error_records_code_message_and_details(self) -> None:
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
                    id="pt-err",
                    project_id="p1",
                    actor_user_id=None,
                    kind="search_rebuild",
                    status="queued",
                    idempotency_key="search_rebuild:p1:v1",
                    params_json=None,
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        app_error = AppError.validation(
            "bad input",
            details={"api_key": "sk-test-SECRET1234", "hint": "x"},
        )

        with patch.object(project_task_service, "SessionLocal", SessionLocal):
            with patch(
                "app.services.search_index_service.rebuild_project_search_index_async",
                side_effect=app_error,
            ):
                project_task_service.run_project_task(task_id="pt-err")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-err")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("error_type"), "AppError")
            self.assertEqual(err.get("code"), "VALIDATION_ERROR")
            self.assertEqual(err.get("message"), "bad input")

            details = err.get("details") or {}
            self.assertNotIn("api_key", details)
            self.assertEqual(details.get("has_api_key"), True)
            self.assertIn("masked_api_key", details)
            self.assertEqual(details.get("hint"), "x")

