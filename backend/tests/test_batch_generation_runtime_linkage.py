from __future__ import annotations

import json
import unittest
from typing import Generator
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import batch_generation as batch_generation_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.batch_generation_task import BatchGenerationTask
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.llm_profile import LLMProfile
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.models.user import User


def _make_test_app(SessionLocal: sessionmaker) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _test_user_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "rid-batch-runtime"
        user_id = request.headers.get("X-Test-User")
        request.state.user_id = user_id
        request.state.authenticated_user_id = user_id
        request.state.session_expire_at = None
        request.state.auth_source = "test"
        return await call_next(request)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(batch_generation_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestBatchGenerationRuntimeLinkage(unittest.TestCase):
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
                LLMProfile.__table__,
                GenerationRun.__table__,
                Project.__table__,
                Outline.__table__,
                Chapter.__table__,
                ProjectTask.__table__,
                ProjectTaskEvent.__table__,
                BatchGenerationTask.__table__,
            ],
        )
        from app.models.batch_generation_task import BatchGenerationTaskItem

        BatchGenerationTaskItem.__table__.create(bind=engine)

        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            project = Project(id="p1", owner_user_id="u_owner", active_outline_id="o1", name="Project 1", genre=None, logline=None)
            db.add(project)
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md="", structure_json=None))
            db.add(Chapter(id="c1", project_id="p1", outline_id="o1", number=1, title="第一章", plan="", content_md=None, summary=None))
            db.commit()

    def test_create_batch_task_creates_linked_project_task(self) -> None:
        client = TestClient(self.app)

        class _NoopQueue:
            def enqueue_batch_generation_task(self, task_id: str) -> str:
                return task_id

        with patch("app.api.routes.batch_generation.get_task_queue", return_value=_NoopQueue()):
            resp = client.post(
                "/api/projects/p1/batch_generation_tasks",
                headers={"X-Test-User": "u_owner"},
                json={"count": 1, "include_existing": True},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json().get("data") or {}
        task = payload.get("task") or {}
        self.assertTrue(str(task.get("project_task_id") or "").strip())
        self.assertEqual(task.get("failed_count"), 0)
        self.assertEqual(task.get("skipped_count"), 0)
        self.assertFalse(bool(task.get("pause_requested")))

        with self.SessionLocal() as db:
            batch_task = db.get(BatchGenerationTask, task.get("id"))
            self.assertIsNotNone(batch_task)
            assert batch_task is not None
            self.assertTrue(str(batch_task.project_task_id or "").strip())
            self.assertTrue(str(batch_task.checkpoint_json or "").strip())

            runtime_task = db.get(ProjectTask, batch_task.project_task_id)
            self.assertIsNotNone(runtime_task)
            assert runtime_task is not None
            self.assertEqual(runtime_task.kind, "batch_generation_orchestrator")
            self.assertEqual(runtime_task.status, "queued")
            params = json.loads(runtime_task.params_json or "{}")
            self.assertEqual(params.get("batch_task_id"), batch_task.id)

            events = db.execute(
                select(ProjectTaskEvent)
                .where(ProjectTaskEvent.task_id == runtime_task.id)
                .order_by(ProjectTaskEvent.seq.asc())
            ).scalars().all()
            self.assertEqual([event.event_type for event in events], ["queued"])

    def test_cancel_queued_batch_updates_linked_project_task(self) -> None:
        client = TestClient(self.app)

        class _NoopQueue:
            def enqueue_batch_generation_task(self, task_id: str) -> str:
                return task_id

        with patch("app.api.routes.batch_generation.get_task_queue", return_value=_NoopQueue()):
            created = client.post(
                "/api/projects/p1/batch_generation_tasks",
                headers={"X-Test-User": "u_owner"},
                json={"count": 1, "include_existing": True},
            )

        batch_task_id = ((created.json().get("data") or {}).get("task") or {}).get("id")
        self.assertTrue(str(batch_task_id or "").strip())

        resp = client.post(f"/api/batch_generation_tasks/{batch_task_id}/cancel", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json().get("data") or {}
        self.assertTrue(bool(payload.get("canceled")))
        self.assertEqual((payload.get("task") or {}).get("status"), "canceled")

        with self.SessionLocal() as db:
            batch_task = db.get(BatchGenerationTask, batch_task_id)
            self.assertIsNotNone(batch_task)
            assert batch_task is not None
            runtime_task = db.get(ProjectTask, batch_task.project_task_id)
            self.assertIsNotNone(runtime_task)
            assert runtime_task is not None
            self.assertEqual(runtime_task.status, "canceled")

            event_types = db.execute(
                select(ProjectTaskEvent.event_type)
                .where(ProjectTaskEvent.task_id == runtime_task.id)
                .order_by(ProjectTaskEvent.seq.asc())
            ).scalars().all()
            self.assertEqual(event_types, ["queued", "canceled"])
