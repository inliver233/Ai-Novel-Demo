from __future__ import annotations

import json
import unittest
from typing import Generator

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
from app.models.batch_generation_task import BatchGenerationTask, BatchGenerationTaskItem
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.models.user import User


def _make_test_app(SessionLocal: sessionmaker) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _test_user_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "rid-runtime-view"
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


class TestProjectTaskRuntimeView(unittest.TestCase):
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
                GenerationRun.__table__,
                Project.__table__,
                Outline.__table__,
                Chapter.__table__,
                ProjectTask.__table__,
                ProjectTaskEvent.__table__,
                BatchGenerationTask.__table__,
            ],
        )
        BatchGenerationTaskItem.__table__.create(bind=engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", active_outline_id="o1", name="Project 1", genre=None, logline=None))
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md="", structure_json=None))
            db.add(Chapter(id="c1", project_id="p1", outline_id="o1", number=1, title="第一章", plan="计划1", content_md="seed", summary="seed"))
            db.add(Chapter(id="c2", project_id="p1", outline_id="o1", number=2, title="第二章", plan="计划2", content_md=None, summary=None))
            db.add(GenerationRun(id="gr-1", project_id="p1", actor_user_id="u_owner", chapter_id="c1", type="chapter", provider=None, model=None, request_id="rid-1", prompt_system=None, prompt_user=None, params_json=None, output_text="ok", error_json=None))
            db.add(
                ProjectTask(
                    id="pt-batch",
                    project_id="p1",
                    actor_user_id="u_owner",
                    kind="batch_generation_orchestrator",
                    status="paused",
                    idempotency_key="batch_generation:bt-1",
                    params_json=json.dumps({"batch_task_id": "bt-1"}, ensure_ascii=False),
                    result_json=json.dumps({"paused": True}, ensure_ascii=False),
                    error_json=json.dumps({"code": "MOCK_FAIL", "message": "step failed"}, ensure_ascii=False),
                )
            )
            db.add(
                BatchGenerationTask(
                    id="bt-1",
                    project_id="p1",
                    outline_id="o1",
                    actor_user_id="u_owner",
                    project_task_id="pt-batch",
                    status="paused",
                    total_count=2,
                    completed_count=1,
                    failed_count=1,
                    skipped_count=0,
                    cancel_requested=False,
                    pause_requested=True,
                    params_json=json.dumps({"runtime_provider": "openai_compatible"}, ensure_ascii=False),
                    checkpoint_json=json.dumps({"status": "paused", "completed_count": 1, "failed_count": 1}, ensure_ascii=False),
                    error_json=json.dumps({"code": "MOCK_FAIL", "message": "step failed"}, ensure_ascii=False),
                )
            )
            db.add_all(
                [
                    BatchGenerationTaskItem(
                        id="item-1",
                        task_id="bt-1",
                        chapter_id="c1",
                        chapter_number=1,
                        status="succeeded",
                        attempt_count=1,
                        generation_run_id="gr-1",
                        last_request_id="rid-1",
                        error_message=None,
                        last_error_json=None,
                    ),
                    BatchGenerationTaskItem(
                        id="item-2",
                        task_id="bt-1",
                        chapter_id="c2",
                        chapter_number=2,
                        status="failed",
                        attempt_count=2,
                        generation_run_id=None,
                        last_request_id="rid-2",
                        error_message="mock fail",
                        last_error_json=json.dumps({"code": "MOCK_FAIL", "message": "step failed"}, ensure_ascii=False),
                    ),
                ]
            )
            payloads = [
                (
                    "running",
                    {
                        "source": "batch_generation_worker",
                        "reason": "batch_generation_worker_start",
                        "checkpoint": {"status": "running", "completed_count": 0, "failed_count": 0},
                    },
                ),
                (
                    "step_started",
                    {
                        "source": "batch_generation_worker",
                        "reason": "chapter_started",
                        "step": {"item_id": "item-1", "chapter_id": "c1", "chapter_number": 1, "status": "running", "attempt_count": 1, "request_id": "rid-1"},
                        "checkpoint": {"status": "running", "completed_count": 0, "failed_count": 0},
                    },
                ),
                (
                    "step_succeeded",
                    {
                        "source": "batch_generation_worker",
                        "reason": "chapter_succeeded",
                        "step": {
                            "item_id": "item-1",
                            "chapter_id": "c1",
                            "chapter_number": 1,
                            "status": "succeeded",
                            "attempt_count": 1,
                            "generation_run_id": "gr-1",
                            "request_id": "rid-1",
                        },
                        "checkpoint": {"status": "running", "completed_count": 1, "failed_count": 0},
                    },
                ),
                (
                    "step_failed",
                    {
                        "source": "batch_generation_worker",
                        "reason": "chapter_failed",
                        "step": {
                            "item_id": "item-2",
                            "chapter_id": "c2",
                            "chapter_number": 2,
                            "status": "failed",
                            "attempt_count": 2,
                            "request_id": "rid-2",
                            "error_message": "mock fail",
                        },
                        "checkpoint": {"status": "paused", "completed_count": 1, "failed_count": 1},
                        "error": {"code": "MOCK_FAIL", "message": "step failed"},
                    },
                ),
                (
                    "paused",
                    {
                        "source": "batch_generation_worker",
                        "reason": "chapter_failed",
                        "checkpoint": {"status": "paused", "completed_count": 1, "failed_count": 1},
                        "error": {"code": "MOCK_FAIL", "message": "step failed"},
                    },
                ),
            ]
            for event_type, payload in payloads:
                db.add(
                    ProjectTaskEvent(
                        project_id="p1",
                        task_id="pt-batch",
                        kind="batch_generation_orchestrator",
                        event_type=event_type,
                        payload_json=json.dumps(payload, ensure_ascii=False),
                    )
                )
            db.commit()

    def test_runtime_endpoint_returns_timeline_steps_artifacts_and_batch_snapshot(self) -> None:
        client = TestClient(self.app)

        resp = client.get("/api/tasks/pt-batch/runtime", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data") or {}

        run = data.get("run") or {}
        self.assertEqual(run.get("id"), "pt-batch")
        self.assertEqual(run.get("status"), "paused")

        timeline = data.get("timeline") or []
        self.assertEqual([entry.get("event_type") for entry in timeline], ["running", "step_started", "step_succeeded", "step_failed", "paused"])

        checkpoints = data.get("checkpoints") or []
        self.assertEqual(len(checkpoints), 5)
        self.assertEqual(((checkpoints[-1] or {}).get("checkpoint") or {}).get("status"), "paused")

        steps = data.get("steps") or []
        self.assertEqual(len(steps), 2)
        self.assertEqual([step.get("chapter_number") for step in steps], [1, 2])
        self.assertEqual(steps[0].get("generation_run_id"), "gr-1")
        self.assertEqual(steps[0].get("status"), "succeeded")
        self.assertEqual(steps[1].get("status"), "failed")
        self.assertEqual((steps[1].get("error") or {}).get("code"), "MOCK_FAIL")

        artifacts = data.get("artifacts") or []
        self.assertEqual(artifacts, [{"kind": "generation_run", "id": "gr-1", "chapter_id": "c1", "chapter_number": 1, "request_id": "rid-1", "event_seq": 3}])

        batch = data.get("batch") or {}
        self.assertEqual(((batch.get("task") or {}).get("id")), "bt-1")
        self.assertEqual(len(batch.get("items") or []), 2)
        self.assertEqual((batch.get("items") or [])[1].get("status"), "failed")
