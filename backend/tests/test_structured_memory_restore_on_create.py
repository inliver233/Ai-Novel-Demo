from __future__ import annotations

import unittest
from typing import Generator

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
from app.db.utils import utc_now
from app.main import app_error_handler, validation_error_handler
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.structured_memory import MemoryChangeSet, MemoryChangeSetItem, MemoryEntity
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


class TestStructuredMemoryRestoreOnCreate(unittest.TestCase):
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
                ProjectMembership.__table__,
                GenerationRun.__table__,
                MemoryEntity.__table__,
                MemoryChangeSet.__table__,
                MemoryChangeSetItem.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add_all(
                [
                    User(id="u_owner", display_name="owner"),
                    User(id="u_editor", display_name="editor"),
                ]
            )
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(ProjectMembership(project_id="p1", user_id="u_editor", role="editor"))
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md=None, structure_json=None))
            db.add(Chapter(id="c1", project_id="p1", outline_id="o1", number=1, title="Ch1", status="done"))
            db.add(
                MemoryEntity(
                    id="e_alice",
                    project_id="p1",
                    entity_type="character",
                    name="Alice",
                    summary_md=None,
                    attributes_json=None,
                    deleted_at=utc_now(),
                )
            )
            db.commit()

    def test_propose_and_apply_restores_soft_deleted_entity_without_target_id(self) -> None:
        client = TestClient(self.app)
        propose = client.post(
            "/api/chapters/c1/memory/propose",
            headers={"X-Test-User": "u_editor"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-restore-entity-1",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "after": {"entity_type": "character", "name": "Alice", "attributes": {"age": 18}},
                    }
                ],
            },
        )
        self.assertEqual(propose.status_code, 200)
        items = propose.json()["data"]["items"]
        self.assertEqual(items[0]["target_id"], "e_alice")

        change_set_id = propose.json()["data"]["change_set"]["id"]
        apply_ok = client.post(
            f"/api/memory_change_sets/{change_set_id}/apply",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(apply_ok.status_code, 200)

        with self.SessionLocal() as db:
            e = db.get(MemoryEntity, "e_alice")
            self.assertIsNotNone(e)
            self.assertIsNone(e.deleted_at)
            self.assertIsNotNone(e.attributes_json)


if __name__ == "__main__":
    unittest.main()
