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
from app.services.project_task_event_service import append_project_task_event


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


def _parse_sse_frames(raw: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        item: dict[str, object] = {}
        for line in block.splitlines():
            if line.startswith("id: "):
                item["id"] = line[4:].strip()
            elif line.startswith("event: "):
                item["event"] = line[7:].strip()
            elif line.startswith("data: "):
                item["data"] = json.loads(line[6:])
        if item:
            frames.append(item)
    return frames


class TestProjectTaskEventsSseEndpoint(unittest.TestCase):
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
            task = ProjectTask(
                id="pt1",
                project_id="p1",
                actor_user_id="u_owner",
                kind="worldbook_auto_update",
                status="queued",
                idempotency_key="worldbook:chapter:c1:since:T1:v1",
                params_json=json.dumps({"chapter_id": "c1"}, ensure_ascii=False),
                result_json=None,
                error_json=None,
            )
            db.add(task)
            db.flush()
            append_project_task_event(db, task=task, event_type="queued", source="seed", payload={"reason": "seed"})
            append_project_task_event(db, task=task, event_type="running", source="seed", payload={"reason": "seed-running"})
            task.status = "succeeded"
            task.result_json = json.dumps({"ok": True}, ensure_ascii=False)
            append_project_task_event(db, task=task, event_type="succeeded", source="seed", payload={"reason": "seed-success"})
            db.commit()

    def test_first_connect_returns_snapshot_with_cursor(self) -> None:
        client = TestClient(self.app)
        with patch("app.api.routes.tasks.SessionLocal", self.SessionLocal):
            resp = client.get(
                "/api/projects/p1/task-events/stream?stream_timeout_seconds=0.2",
                headers={"X-Test-User": "u_owner"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "text/event-stream; charset=utf-8")
        frames = _parse_sse_frames(resp.text)
        self.assertGreaterEqual(len(frames), 1)
        first = frames[0]
        self.assertEqual(first.get("event"), "snapshot")
        self.assertEqual(first.get("id"), "3")
        data = first.get("data") or {}
        assert isinstance(data, dict)
        self.assertEqual(data.get("type"), "snapshot")
        self.assertEqual(data.get("project_id"), "p1")
        self.assertEqual(data.get("cursor"), 3)
        self.assertEqual(data.get("active_tasks"), [])

    def test_last_event_id_replays_missing_events_in_order(self) -> None:
        client = TestClient(self.app)
        with patch("app.api.routes.tasks.SessionLocal", self.SessionLocal):
            resp = client.get(
                "/api/projects/p1/task-events/stream?stream_timeout_seconds=0.2",
                headers={"X-Test-User": "u_owner", "Last-Event-ID": "1"},
            )

        self.assertEqual(resp.status_code, 200)
        frames = _parse_sse_frames(resp.text)
        self.assertEqual([frame.get("event") for frame in frames], ["project_task", "project_task"])
        self.assertEqual([frame.get("id") for frame in frames], ["2", "3"])
        data = [frame.get("data") or {} for frame in frames]
        self.assertEqual([item.get("event_type") for item in data], ["running", "succeeded"])
        self.assertEqual([item.get("seq") for item in data], [2, 3])
        self.assertEqual([item.get("type") for item in data], ["event", "event"])
