from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.models.memory_task import MemoryTask
from app.services import memory_update_service


class TestMemoryTaskWorkerAppError(unittest.TestCase):
    def test_app_error_records_code_message_and_details(self) -> None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)

        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql(
                "CREATE TABLE memory_change_sets (id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36))"
            )
            conn.exec_driver_sql("INSERT INTO projects (id) VALUES ('p1')")
            conn.exec_driver_sql("INSERT INTO memory_change_sets (id, project_id) VALUES ('cs1','p1')")

        MemoryTask.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with SessionLocal() as db:
            db.add(
                MemoryTask(
                    id="mt-err",
                    project_id="p1",
                    change_set_id="cs1",
                    actor_user_id=None,
                    kind="fractal_rebuild",
                    status="queued",
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

        with patch.object(memory_update_service, "SessionLocal", SessionLocal):
            with patch.object(memory_update_service, "rebuild_fractal_memory", side_effect=app_error):
                memory_update_service.run_memory_task(task_id="mt-err")

        with SessionLocal() as db:
            task = db.get(MemoryTask, "mt-err")
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
