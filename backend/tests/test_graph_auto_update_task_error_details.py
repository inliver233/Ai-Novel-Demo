from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.services import project_task_service


class TestGraphAutoUpdateTaskErrorDetails(unittest.TestCase):
    def test_graph_auto_update_failed_records_how_to_fix_and_run_id(self) -> None:
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
                    id="pt-graph",
                    project_id="p1",
                    actor_user_id="u1",
                    kind="graph_auto_update",
                    status="queued",
                    idempotency_key="graph_ai:ch:c1:since:token:v1",
                    params_json=json.dumps(
                        {"chapter_id": "c1", "focus": None, "request_id": "rid-test"},
                        ensure_ascii=False,
                    ),
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        failure = {
            "ok": False,
            "project_id": "p1",
            "chapter_id": "c1",
            "reason": "parse_failed",
            "run_id": "run-test-graph",
            "warnings": ["w1"],
            "parse_error": {"code": "MEMORY_UPDATE_PARSE_ERROR", "message": "bad schema"},
        }

        with patch.object(project_task_service, "SessionLocal", SessionLocal), patch(
            "app.services.graph_auto_update_service.graph_auto_update_v1", return_value=failure
        ):
            project_task_service.run_project_task(task_id="pt-graph")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-graph")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("error_type"), "AppError")
            self.assertEqual(err.get("code"), "GRAPH_AUTO_UPDATE_FAILED")

            details = err.get("details") or {}
            self.assertEqual(details.get("reason"), "parse_failed")
            self.assertEqual(details.get("run_id"), "run-test-graph")
            self.assertIsInstance(details.get("how_to_fix"), list)
            self.assertGreaterEqual(len(details.get("how_to_fix") or []), 1)

    def test_graph_auto_update_llm_call_failed_records_attempts(self) -> None:
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
                    id="pt-graph-llm-failed",
                    project_id="p1",
                    actor_user_id="u1",
                    kind="graph_auto_update",
                    status="queued",
                    idempotency_key="graph_ai:ch:c1:since:token:v1",
                    params_json=json.dumps(
                        {"chapter_id": "c1", "focus": None, "request_id": "rid-test"},
                        ensure_ascii=False,
                    ),
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        failure = {
            "ok": False,
            "project_id": "p1",
            "chapter_id": "c1",
            "reason": "llm_call_failed",
            "run_id": "run-test-graph",
            "error_type": "TimeoutError",
            "error_message": "boom",
            "attempts": [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test-graph", "error_code": "LLM_TIMEOUT"}],
            "error": {"code": "LLM_TIMEOUT", "details": {"attempts": [{"attempt": 1, "request_id": "rid-test"}]}},
        }

        with patch.object(project_task_service, "SessionLocal", SessionLocal), patch(
            "app.services.graph_auto_update_service.graph_auto_update_v1", return_value=failure
        ):
            project_task_service.run_project_task(task_id="pt-graph-llm-failed")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-graph-llm-failed")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("error_type"), "AppError")
            self.assertEqual(err.get("code"), "GRAPH_AUTO_UPDATE_FAILED")

            details = err.get("details") or {}
            self.assertEqual(details.get("reason"), "llm_call_failed")
            self.assertEqual(details.get("run_id"), "run-test-graph")
            self.assertIsInstance(details.get("attempts"), list)
            self.assertGreaterEqual(len(details.get("attempts") or []), 1)
