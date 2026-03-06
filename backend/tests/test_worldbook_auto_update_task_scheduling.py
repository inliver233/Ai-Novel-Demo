from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.services.project_task_service import schedule_worldbook_auto_update_task


class _RecordingQueue:
    def __init__(self, *, raise_on_enqueue: bool = False) -> None:
        self.raise_on_enqueue = raise_on_enqueue
        self.calls: list[tuple[str, str]] = []

    def enqueue(self, *, kind: str, task_id: str) -> str:
        self.calls.append((str(kind), str(task_id)))
        if self.raise_on_enqueue:
            raise RuntimeError("enqueue_failed")
        return str(task_id)

    def enqueue_batch_generation_task(self, task_id: str) -> str:  # pragma: no cover
        return self.enqueue(kind="batch_generation", task_id=task_id)


class TestWorldbookAutoUpdateTaskScheduling(unittest.TestCase):
    def _make_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO projects (id) VALUES ('project-1')")
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO users (id) VALUES ('user-1')")
        ProjectTask.__table__.create(engine)
        ProjectTaskEvent.__table__.create(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return SessionLocal

    def test_same_token_is_idempotent(self) -> None:
        SessionLocal = self._make_db()
        q = _RecordingQueue()

        with SessionLocal() as db, patch("app.services.task_queue.get_task_queue", return_value=q):
            t1 = schedule_worldbook_auto_update_task(
                db=db,
                project_id="project-1",
                actor_user_id=None,
                request_id="r1",
                chapter_id="chapter-1",
                chapter_token="T1",
                reason="chapter_done",
            )
            t2 = schedule_worldbook_auto_update_task(
                db=db,
                project_id="project-1",
                actor_user_id=None,
                request_id="r2",
                chapter_id="chapter-1",
                chapter_token="T1",
                reason="chapter_done",
            )

            self.assertEqual(t1, t2)
            rows = db.execute(select(ProjectTask).order_by(ProjectTask.id)).scalars().all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].idempotency_key, "worldbook:chapter:chapter-1:since:T1:v1")

    def test_different_token_creates_new_task(self) -> None:
        SessionLocal = self._make_db()
        q = _RecordingQueue()

        with SessionLocal() as db, patch("app.services.task_queue.get_task_queue", return_value=q):
            t1 = schedule_worldbook_auto_update_task(
                db=db,
                project_id="project-1",
                actor_user_id=None,
                request_id="r1",
                chapter_id="chapter-1",
                chapter_token="T1",
                reason="chapter_done",
            )
            t2 = schedule_worldbook_auto_update_task(
                db=db,
                project_id="project-1",
                actor_user_id=None,
                request_id="r2",
                chapter_id="chapter-1",
                chapter_token="T2",
                reason="chapter_done",
            )

            self.assertNotEqual(t1, t2)
            rows = db.execute(select(ProjectTask).order_by(ProjectTask.id)).scalars().all()
            self.assertEqual(len(rows), 2)
            keys = sorted([r.idempotency_key for r in rows])
            self.assertEqual(keys, ["worldbook:chapter:chapter-1:since:T1:v1", "worldbook:chapter:chapter-1:since:T2:v1"])

    def test_failed_task_can_be_rescheduled_as_retry(self) -> None:
        SessionLocal = self._make_db()
        q_fail = _RecordingQueue(raise_on_enqueue=True)
        q_ok = _RecordingQueue()

        with SessionLocal() as db:
            with patch("app.services.task_queue.get_task_queue", return_value=q_fail):
                task_id = schedule_worldbook_auto_update_task(
                    db=db,
                    project_id="project-1",
                    actor_user_id=None,
                    request_id="r1",
                    chapter_id="chapter-1",
                    chapter_token="T1",
                    reason="chapter_done",
                )
            row = db.get(ProjectTask, str(task_id))
            assert row is not None
            self.assertEqual(str(row.status), "failed")
            self.assertIsNotNone(row.error_json)

            with patch("app.services.task_queue.get_task_queue", return_value=q_ok):
                task_id2 = schedule_worldbook_auto_update_task(
                    db=db,
                    project_id="project-1",
                    actor_user_id=None,
                    request_id="r2",
                    chapter_id="chapter-1",
                    chapter_token="T1",
                    reason="chapter_done",
                )

            self.assertEqual(task_id, task_id2)
            row2 = db.get(ProjectTask, str(task_id2))
            assert row2 is not None
            self.assertEqual(str(row2.status), "queued")
            self.assertIsNone(row2.error_json)
            value = json.loads(row2.params_json or "{}")
            self.assertEqual(int(value.get("retry_count") or 0), 1)

    def test_actor_user_id_is_filled_for_system_triggered_task(self) -> None:
        SessionLocal = self._make_db()
        q = _RecordingQueue()

        with SessionLocal() as db, patch("app.services.task_queue.get_task_queue", return_value=q):
            task_id = schedule_worldbook_auto_update_task(
                db=db,
                project_id="project-1",
                actor_user_id=None,
                request_id="r1",
                chapter_id="chapter-1",
                chapter_token="T1",
                reason="chapter_done",
            )
            row = db.get(ProjectTask, str(task_id))
            assert row is not None
            self.assertIsNone(row.actor_user_id)

            task_id2 = schedule_worldbook_auto_update_task(
                db=db,
                project_id="project-1",
                actor_user_id="user-1",
                request_id="r2",
                chapter_id="chapter-1",
                chapter_token="T1",
                reason="manual_worldbook_auto_update",
            )

            self.assertEqual(task_id, task_id2)
            row2 = db.get(ProjectTask, str(task_id2))
            assert row2 is not None
            self.assertEqual(row2.actor_user_id, "user-1")

