from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import graph as graph_routes
from app.core.errors import AppError
from app.db.base import Base
from app.main import app_error_handler, validation_error_handler
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.models.user import User


class _DummyQueue:
    def enqueue(self, *, kind: str, task_id: str) -> None:
        return None


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
    app.include_router(graph_routes.router, prefix="/api")

    return app


class TestGraphAutoUpdateTriggerEndpoint(unittest.TestCase):
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
                Outline.__table__,
                Chapter.__table__,
                ProjectTask.__table__,
                ProjectTaskEvent.__table__,
            ],
        )

        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(Outline(id="o1", project_id="p1", title="Outline 1", content_md=None, structure_json=None))
            db.add(
                Chapter(
                    id="c1",
                    project_id="p1",
                    outline_id="o1",
                    number=1,
                    title="Chapter 1",
                    plan="hello",
                    content_md="content",
                    summary="summary",
                    status="done",
                )
            )
            db.commit()

    def test_trigger_graph_auto_update_requires_chapter_id(self) -> None:
        client = TestClient(self.app)
        with patch.object(graph_routes, "SessionLocal", self.SessionLocal):
            resp = client.post("/api/projects/p1/graph/auto_update", headers={"X-Test-User": "u_owner"}, json={})

        self.assertEqual(resp.status_code, 400)
        payload = resp.json()
        self.assertFalse(payload.get("ok"))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "VALIDATION_ERROR")
        self.assertIn("chapter_id", str(err.get("message") or ""))

    def test_trigger_graph_auto_update_returns_task_id(self) -> None:
        client = TestClient(self.app)
        with patch.object(graph_routes, "SessionLocal", self.SessionLocal), patch(
            "app.services.task_queue.get_task_queue", return_value=_DummyQueue()
        ):
            resp = client.post(
                "/api/projects/p1/graph/auto_update",
                headers={"X-Test-User": "u_owner"},
                json={"chapter_id": "c1", "focus": "dragon"},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))
        task_id = str((payload.get("data") or {}).get("task_id") or "")
        self.assertTrue(task_id)

        with self.SessionLocal() as db:
            task = db.get(ProjectTask, task_id)
            self.assertIsNotNone(task)
            self.assertEqual(str(task.kind or ""), "graph_auto_update")
            self.assertEqual(str(task.project_id or ""), "p1")
            self.assertEqual(str(task.actor_user_id or ""), "u_owner")
            self.assertEqual(str(task.status or ""), "queued")

