from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.services import project_task_service


class TestProjectTaskWorkerNoop(unittest.TestCase):
    def test_noop_task_runs_and_records_result(self) -> None:
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
                    id="pt-1",
                    project_id="p1",
                    actor_user_id=None,
                    kind="noop",
                    status="queued",
                    idempotency_key="noop:1",
                    params_json=None,
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        with patch.object(project_task_service, "SessionLocal", SessionLocal):
            project_task_service.run_project_task(task_id="pt-1")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-1")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "succeeded")
            self.assertIsNotNone(task.result_json)
            result = json.loads(task.result_json or "{}")
            self.assertEqual(result.get("skipped"), True)
            self.assertIsNotNone(task.finished_at)

    def test_canceled_task_is_skipped(self) -> None:
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
                    id="pt-canceled",
                    project_id="p1",
                    actor_user_id=None,
                    kind="noop",
                    status="canceled",
                    idempotency_key="noop:canceled:1",
                    params_json=None,
                    result_json=None,
                    error_json=None,
                )
            )
            db.commit()

        with patch.object(project_task_service, "SessionLocal", SessionLocal):
            project_task_service.run_project_task(task_id="pt-canceled")

        with SessionLocal() as db:
            task = db.get(ProjectTask, "pt-canceled")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "canceled")
            self.assertIsNone(task.result_json)
            self.assertIsNotNone(task.finished_at)
