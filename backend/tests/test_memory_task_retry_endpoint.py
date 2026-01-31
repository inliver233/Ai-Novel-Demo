from __future__ import annotations

import json
import unittest
from typing import Generator
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import memory as memory_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.memory_task import MemoryTask
from app.models.project import Project
from app.models.structured_memory import MemoryChangeSet
from app.models.user import User


def _make_test_app(SessionLocal: sessionmaker) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _test_user_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "rid-test"
        user_id = request.headers.get("X-Test-User")
        request.state.user_id = user_id
        request.state.authenticated_user_id = user_id
        request.state.session_expire_at = None
        request.state.auth_source = "test"
        return await call_next(request)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(memory_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestMemoryTaskRetryEndpoint(unittest.TestCase):
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
                MemoryChangeSet.__table__,
                MemoryTask.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(
                MemoryChangeSet(
                    id="cs1",
                    project_id="p1",
                    actor_user_id="u_owner",
                    generation_run_id=None,
                    request_id="rid-cs",
                    idempotency_key="k1",
                    title="t",
                    summary_md=None,
                    status="proposed",
                )
            )
            db.add(
                MemoryTask(
                    id="t1",
                    project_id="p1",
                    change_set_id="cs1",
                    actor_user_id="u_owner",
                    kind="vector_rebuild",
                    status="failed",
                    params_json=None,
                    result_json=None,
                    error_json=json.dumps({"error_type": "X", "message": "boom"}, ensure_ascii=False),
                )
            )
            db.commit()

    def test_retry_failed_task_sets_queued_and_is_idempotent(self) -> None:
        client = TestClient(self.app)

        class _NoopQueue:
            def enqueue(self, *, kind: str, task_id: str) -> str:  # type: ignore[no-untyped-def]
                return task_id

            def enqueue_batch_generation_task(self, task_id: str) -> str:
                return task_id

        with patch("app.services.task_queue.get_task_queue", return_value=_NoopQueue()):
            resp = client.post("/api/memory_tasks/t1/retry", headers={"X-Test-User": "u_owner"})

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))
        data = payload.get("data") or {}
        self.assertEqual(data.get("status"), "queued")

        with self.SessionLocal() as db:
            task = db.get(MemoryTask, "t1")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "queued")
            self.assertIsNone(task.error_json)
            self.assertIsNotNone(task.params_json)

        with patch("app.services.task_queue.get_task_queue", return_value=_NoopQueue()):
            resp2 = client.post("/api/memory_tasks/t1/retry", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json().get("data") or {}
        self.assertEqual(data2.get("status"), "queued")

    def test_retry_enqueue_failure_records_error_and_returns_503(self) -> None:
        client = TestClient(self.app)

        class _FailQueue:
            def enqueue(self, *, kind: str, task_id: str) -> str:  # type: ignore[no-untyped-def]
                raise AppError(
                    code="QUEUE_UNAVAILABLE",
                    message="任务队列不可用：请启动 Redis + worker，或切换 TASK_QUEUE_BACKEND=inline（仅 dev/test）",
                    status_code=503,
                    details={"how_to_fix": ["start redis", "start worker"]},
                )

            def enqueue_batch_generation_task(self, task_id: str) -> str:
                return task_id

        with patch("app.services.task_queue.get_task_queue", return_value=_FailQueue()):
            resp = client.post("/api/memory_tasks/t1/retry", headers={"X-Test-User": "u_owner"})

        self.assertEqual(resp.status_code, 503)
        payload = resp.json()
        self.assertFalse(payload.get("ok"))
        self.assertEqual((payload.get("error") or {}).get("code"), "QUEUE_UNAVAILABLE")

        with self.SessionLocal() as db:
            task = db.get(MemoryTask, "t1")
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "failed")
            err = json.loads(task.error_json or "{}")
            self.assertEqual(err.get("error_type"), "AppError")
            self.assertEqual(err.get("code"), "QUEUE_UNAVAILABLE")
            self.assertTrue(str(err.get("message") or "").strip())
            self.assertIn("details", err)
