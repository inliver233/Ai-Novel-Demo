from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.batch_generation_task import BatchGenerationTask
from app.services import batch_generation_service


class TestBatchGenerationWorkerTerminalNoop(unittest.TestCase):
    def test_succeeded_task_is_noop(self) -> None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE outlines (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE project_tasks (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE generation_runs (id VARCHAR(36) PRIMARY KEY)")
        BatchGenerationTask.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with SessionLocal() as db:
            db.add(
                BatchGenerationTask(
                    id="task-1",
                    project_id="project-1",
                    outline_id="outline-1",
                    actor_user_id=None,
                    status="succeeded",
                    total_count=0,
                    completed_count=0,
                    cancel_requested=False,
                    params_json=None,
                    error_json=None,
                )
            )
            db.commit()

        with patch.object(batch_generation_service, "SessionLocal", SessionLocal):
            batch_generation_service.run_batch_generation_task(task_id="task-1")

        with SessionLocal() as db:
            task = db.get(BatchGenerationTask, "task-1")
            self.assertIsNotNone(task)
            self.assertEqual(task.status, "succeeded")
