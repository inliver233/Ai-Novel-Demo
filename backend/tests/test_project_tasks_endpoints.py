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

from app.api.routes import tasks as tasks_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
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
    app.include_router(tasks_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestProjectTasksEndpoints(unittest.TestCase):
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
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(
                ProjectTask(
                    id="pt1",
                    project_id="p1",
                    actor_user_id="u_owner",
                    kind="search",
                    status="queued",
                    idempotency_key="search:project:v1",
                    params_json=json.dumps(
                        {"api_key": "sk-test-SECRET1234", "rerank_api_key": "rk-test-SECRET9999"},
                        ensure_ascii=False,
                    ),
                    result_json=None,
                    error_json=None,
                )
            )
            db.add(
                ProjectTask(
                    id="pt2",
                    project_id="p1",
                    actor_user_id="u_owner",
                    kind="vector",
                    status="failed",
                    idempotency_key="vector:project:v1",
                    params_json=None,
                    result_json=None,
                    error_json=json.dumps(
                        {"error_type": "X", "message": "boom", "api_key": "sk-test-SECRET1234"},
                        ensure_ascii=False,
                    ),
                )
            )
            db.add(
                ProjectTask(
                    id="pt3",
                    project_id="p1",
                    actor_user_id="u_owner",
                    kind="search",
                    status="succeeded",
                    idempotency_key="search:chapter:c1:v1",
                    params_json=None,
                    result_json=json.dumps({"ok": True}, ensure_ascii=False),
                    error_json=None,
                )
            )
            db.commit()

    def test_list_filters_by_kind_and_status(self) -> None:
        client = TestClient(self.app)

        resp = client.get("/api/projects/p1/tasks?kind=search", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        items = (resp.json().get("data") or {}).get("items") or []
        self.assertEqual({it.get("id") for it in items}, {"pt1", "pt3"})

        resp2 = client.get("/api/projects/p1/tasks?status=done", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp2.status_code, 200)
        items2 = (resp2.json().get("data") or {}).get("items") or []
        self.assertEqual([it.get("id") for it in items2], ["pt3"])
        self.assertEqual(items2[0].get("status"), "done")

    def test_get_redacts_api_keys(self) -> None:
        client = TestClient(self.app)

        resp = client.get("/api/tasks/pt1", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data") or {}
        params = data.get("params") or {}
        self.assertNotIn("api_key", params)
        self.assertIn("has_api_key", params)
        self.assertIn("masked_api_key", params)
        self.assertNotIn("rerank_api_key", params)
        self.assertIn("rerank_has_api_key", params)
        self.assertIn("rerank_masked_api_key", params)

        resp2 = client.get("/api/tasks/pt2", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json().get("data") or {}
        err = data2.get("error") or {}
        self.assertNotIn("api_key", err)
        self.assertIn("has_api_key", err)
        self.assertIn("masked_api_key", err)

    def test_retry_failed_task_sets_queued(self) -> None:
        client = TestClient(self.app)

        class _NoopQueue:
            def enqueue(self, *, kind: str, task_id: str) -> str:  # type: ignore[no-untyped-def]
                return task_id

            def enqueue_batch_generation_task(self, task_id: str) -> str:
                return task_id

        with patch("app.services.task_queue.get_task_queue", return_value=_NoopQueue()):
            resp = client.post("/api/tasks/pt2/retry", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data") or {}
        self.assertEqual(data.get("status"), "queued")
        self.assertIsNone(data.get("error"))

        with self.SessionLocal() as db:
            row = db.get(ProjectTask, "pt2")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row.status, "queued")
            self.assertIsNone(row.error_json)

    def test_retry_enqueue_failure_records_non_empty_error_message(self) -> None:
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
            resp = client.post("/api/tasks/pt2/retry", headers={"X-Test-User": "u_owner"})

        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data") or {}
        self.assertEqual(data.get("status"), "failed")
        self.assertTrue(str(data.get("error_message") or "").strip())

        err = data.get("error") or {}
        self.assertEqual(err.get("code"), "QUEUE_UNAVAILABLE")
        self.assertTrue(str(err.get("message") or "").strip())

    def test_cancel_queued_task_sets_canceled(self) -> None:
        client = TestClient(self.app)

        resp = client.post("/api/tasks/pt1/cancel", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data") or {}
        self.assertEqual(data.get("status"), "canceled")
        self.assertIsNone(data.get("error"))

        result = data.get("result") or {}
        self.assertEqual(result.get("canceled"), True)
        timings = data.get("timings") or {}
        self.assertTrue(str(timings.get("finished_at") or "").strip())

        with self.SessionLocal() as db:
            row = db.get(ProjectTask, "pt1")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row.status, "canceled")
            self.assertIsNotNone(row.finished_at)
