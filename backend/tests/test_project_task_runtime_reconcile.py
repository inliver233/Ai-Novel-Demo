from __future__ import annotations

import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.utils import utc_now
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.models.user import User
from app.services.project_task_runtime_service import reconcile_project_tasks_once, touch_project_task_heartbeat


class _RecordingQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def enqueue(self, *, kind: str, task_id: str) -> str:
        self.calls.append((kind, task_id))
        return task_id

    def enqueue_batch_generation_task(self, task_id: str) -> str:
        return task_id


class TestProjectTaskRuntimeReconcile(unittest.TestCase):
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
                ProjectTask.__table__,
                ProjectTaskEvent.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_touch_project_task_heartbeat_updates_running_row(self) -> None:
        old_heartbeat = utc_now() - timedelta(minutes=5)
        with self.SessionLocal() as db:
            db.add(
                ProjectTask(
                    id="pt-heartbeat",
                    project_id="p1",
                    actor_user_id="u1",
                    kind="noop",
                    status="running",
                    idempotency_key="heartbeat:v1",
                    params_json=None,
                    result_json=None,
                    error_json=None,
                    heartbeat_at=old_heartbeat,
                    started_at=old_heartbeat,
                    attempt=1,
                )
            )
            db.commit()

        with patch("app.services.project_task_runtime_service.SessionLocal", self.SessionLocal):
            self.assertTrue(touch_project_task_heartbeat(task_id="pt-heartbeat"))

        with self.SessionLocal() as db:
            task = db.get(ProjectTask, "pt-heartbeat")
            assert task is not None
            self.assertEqual(task.status, "running")
            assert task.heartbeat_at is not None
            self.assertNotEqual(task.heartbeat_at.isoformat(), old_heartbeat.isoformat())

    def test_reconcile_times_out_stale_running_and_emits_timeout_event(self) -> None:
        stale_at = utc_now() - timedelta(minutes=10)
        with self.SessionLocal() as db:
            db.add(
                ProjectTask(
                    id="pt-stale",
                    project_id="p1",
                    actor_user_id="u1",
                    kind="noop",
                    status="running",
                    idempotency_key="stale:v1",
                    params_json=None,
                    result_json=None,
                    error_json=None,
                    started_at=stale_at,
                    heartbeat_at=stale_at,
                    attempt=2,
                )
            )
            db.commit()

        with patch("app.services.project_task_runtime_service.SessionLocal", self.SessionLocal):
            summary = reconcile_project_tasks_once(reason="watchdog", now=utc_now())

        self.assertEqual(summary["timed_out_running"], 1)
        with self.SessionLocal() as db:
            task = db.get(ProjectTask, "pt-stale")
            assert task is not None
            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("code"), "PROJECT_TASK_HEARTBEAT_TIMEOUT")
            events = db.execute(select(ProjectTaskEvent).where(ProjectTaskEvent.task_id == "pt-stale").order_by(ProjectTaskEvent.seq.asc())).scalars().all()
            self.assertEqual([event.event_type for event in events], ["timeout"])

    def test_reconcile_requeues_orphan_queued_task_and_emits_system_event(self) -> None:
        created_at = utc_now() - timedelta(minutes=5)
        with self.SessionLocal() as db:
            db.add(
                ProjectTask(
                    id="pt-orphan",
                    project_id="p1",
                    actor_user_id="u1",
                    kind="noop",
                    status="queued",
                    idempotency_key="orphan:v1",
                    params_json=None,
                    result_json=None,
                    error_json=None,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            db.commit()

        queue = _RecordingQueue()
        with patch("app.services.project_task_runtime_service.SessionLocal", self.SessionLocal), patch(
            "app.services.project_task_runtime_service.project_task_queue_has_task",
            return_value=False,
        ), patch("app.services.project_task_runtime_service.get_task_queue", return_value=queue):
            summary = reconcile_project_tasks_once(reason="startup", now=utc_now())

        self.assertEqual(summary["requeued_orphans"], 1)
        self.assertEqual(queue.calls, [("project_task", "pt-orphan")])
        with self.SessionLocal() as db:
            task = db.get(ProjectTask, "pt-orphan")
            assert task is not None
            self.assertEqual(task.status, "queued")
            events = db.execute(select(ProjectTaskEvent).where(ProjectTaskEvent.task_id == "pt-orphan").order_by(ProjectTaskEvent.seq.asc())).scalars().all()
            self.assertEqual([event.event_type for event in events], ["reconcile"])

    def test_reconcile_handles_legacy_sqlite_datetime_rows(self) -> None:
        with self.SessionLocal() as db:
            db.execute(
                text(
                    """
                    insert into project_tasks
                    (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json,
                     created_at, started_at, heartbeat_at, finished_at, attempt, updated_at)
                    values
                    ('pt-legacy', 'p1', 'u1', 'noop', 'running', 'legacy:v1', null, null, null,
                     '2026-03-08 03:29:59', '2026-03-08 03:29:59', '2026-03-08 03:29:59', null, 1, '2026-03-08 03:29:59')
                    """
                )
            )
            db.commit()

        with patch("app.services.project_task_runtime_service.SessionLocal", self.SessionLocal):
            summary = reconcile_project_tasks_once(reason="watchdog", now=utc_now())

        self.assertEqual(summary["timed_out_running"], 1)
        with self.SessionLocal() as db:
            task = db.get(ProjectTask, "pt-legacy")
            assert task is not None
            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("code"), "PROJECT_TASK_HEARTBEAT_TIMEOUT")
