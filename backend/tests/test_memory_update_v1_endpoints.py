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
from app.main import app_error_handler, validation_error_handler
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.structured_memory import (
    MemoryChangeSet,
    MemoryChangeSetItem,
    MemoryEntity,
    MemoryEvidence,
    MemoryEvent,
    MemoryForeshadow,
    MemoryRelation,
)
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


class TestMemoryUpdateV1Endpoints(unittest.TestCase):
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
                MemoryRelation.__table__,
                MemoryEvent.__table__,
                MemoryForeshadow.__table__,
                MemoryEvidence.__table__,
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
                    User(id="u_viewer", display_name="viewer"),
                ]
            )
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(ProjectMembership(project_id="p1", user_id="u_editor", role="editor"))
            db.add(ProjectMembership(project_id="p1", user_id="u_viewer", role="viewer"))
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md=None, structure_json=None))
            db.add(Chapter(id="c1", project_id="p1", outline_id="o1", number=1, title="Ch1", status="done"))
            db.add(Project(id="p2", owner_user_id="u_owner", name="Project 2", genre=None, logline=None))
            db.add(Outline(id="o2", project_id="p2", title="Outline 2", content_md=None, structure_json=None))
            db.add(Chapter(id="c2", project_id="p2", outline_id="o2", number=1, title="Ch2", status="done"))
            db.commit()

    def test_validation_fail_closed(self) -> None:
        client = TestClient(self.app)
        resp = client.post(
            "/api/chapters/c1/memory/propose",
            headers={"X-Test-User": "u_editor"},
            json={"schema_version": "wrong", "idempotency_key": "key-12345678", "ops": []},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "VALIDATION_ERROR")

    def test_viewer_cannot_propose(self) -> None:
        client = TestClient(self.app)
        resp = client.post(
            "/api/chapters/c1/memory/propose",
            headers={"X-Test-User": "u_viewer"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-12345678",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": "e1",
                        "after": {"entity_type": "character", "name": "Alice"},
                    }
                ],
            },
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")

    def test_propose_apply_and_rollback_soft_delete(self) -> None:
        client = TestClient(self.app)

        propose = client.post(
            "/api/chapters/c1/memory/propose",
            headers={"X-Test-User": "u_editor"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-entity-upsert-1",
                "title": "upsert entity",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": "e1",
                        "after": {"entity_type": "character", "name": "Alice", "attributes": {"age": 18}},
                    }
                ],
            },
        )
        self.assertEqual(propose.status_code, 200)
        change_set_id = propose.json()["data"]["change_set"]["id"]

        apply1 = client.post(
            f"/api/memory_change_sets/{change_set_id}/apply",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(apply1.status_code, 200)
        self.assertFalse(bool(apply1.json()["data"]["idempotent"]))

        apply2 = client.post(
            f"/api/memory_change_sets/{change_set_id}/apply",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(apply2.status_code, 200)
        self.assertTrue(bool(apply2.json()["data"]["idempotent"]))

        with self.SessionLocal() as db:
            e1 = db.get(MemoryEntity, "e1")
            self.assertIsNotNone(e1)
            self.assertEqual(e1.project_id, "p1")
            self.assertEqual(e1.name, "Alice")
            self.assertIsNone(e1.deleted_at)

        propose_del = client.post(
            "/api/chapters/c1/memory/propose",
            headers={"X-Test-User": "u_editor"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-entity-delete-1",
                "title": "delete entity",
                "ops": [
                    {
                        "op": "delete",
                        "target_table": "entities",
                        "target_id": "e1",
                    }
                ],
            },
        )
        self.assertEqual(propose_del.status_code, 200)
        del_change_set_id = propose_del.json()["data"]["change_set"]["id"]

        apply_del = client.post(
            f"/api/memory_change_sets/{del_change_set_id}/apply",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(apply_del.status_code, 200)

        with self.SessionLocal() as db:
            e1 = db.get(MemoryEntity, "e1")
            self.assertIsNotNone(e1)
            self.assertIsNotNone(e1.deleted_at)

        rb = client.post(
            f"/api/memory_change_sets/{del_change_set_id}/rollback",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(rb.status_code, 200)

        with self.SessionLocal() as db:
            e1 = db.get(MemoryEntity, "e1")
            self.assertIsNotNone(e1)
            self.assertIsNone(e1.deleted_at)

    def test_change_set_cannot_cross_project_apply(self) -> None:
        client = TestClient(self.app)
        propose = client.post(
            "/api/chapters/c2/memory/propose",
            headers={"X-Test-User": "u_owner"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-cross-project-1",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": "p2_e1",
                        "after": {"entity_type": "character", "name": "Mallory"},
                    }
                ],
            },
        )
        self.assertEqual(propose.status_code, 200)
        change_set_id = propose.json()["data"]["change_set"]["id"]

        apply_forbidden = client.post(
            f"/api/memory_change_sets/{change_set_id}/apply",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(apply_forbidden.status_code, 404)
        self.assertEqual(apply_forbidden.json()["error"]["code"], "NOT_FOUND")

    def test_change_set_cannot_cross_project_rollback(self) -> None:
        client = TestClient(self.app)
        propose = client.post(
            "/api/chapters/c2/memory/propose",
            headers={"X-Test-User": "u_owner"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-cross-project-rb-1",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": "p2_e2",
                        "after": {"entity_type": "character", "name": "Carol"},
                    }
                ],
            },
        )
        self.assertEqual(propose.status_code, 200)
        change_set_id = propose.json()["data"]["change_set"]["id"]

        apply_ok = client.post(
            f"/api/memory_change_sets/{change_set_id}/apply",
            headers={"X-Test-User": "u_owner"},
        )
        self.assertEqual(apply_ok.status_code, 200)

        rollback_forbidden = client.post(
            f"/api/memory_change_sets/{change_set_id}/rollback",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(rollback_forbidden.status_code, 404)
        self.assertEqual(rollback_forbidden.json()["error"]["code"], "NOT_FOUND")

    def test_apply_integrity_error_marks_failed(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                MemoryEntity(
                    id="e_existing",
                    project_id="p1",
                    entity_type="character",
                    name="Alice",
                    summary_md=None,
                    attributes_json=None,
                    deleted_at=None,
                )
            )
            db.commit()

        client = TestClient(self.app)
        propose = client.post(
            "/api/chapters/c1/memory/propose",
            headers={"X-Test-User": "u_editor"},
            json={
                "schema_version": "memory_update_v1",
                "idempotency_key": "key-integrity-error-1",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": "e_conflict",
                        "after": {"entity_type": "character", "name": "Alice"},
                    }
                ],
            },
        )
        self.assertEqual(propose.status_code, 200)
        change_set_id = propose.json()["data"]["change_set"]["id"]

        apply_conflict = client.post(
            f"/api/memory_change_sets/{change_set_id}/apply",
            headers={"X-Test-User": "u_editor"},
        )
        self.assertEqual(apply_conflict.status_code, 409)
        self.assertEqual(apply_conflict.json()["error"]["code"], "CONFLICT")
        self.assertEqual(apply_conflict.json()["error"]["details"]["reason"], "integrity_error")

        with self.SessionLocal() as db:
            change_set = db.get(MemoryChangeSet, change_set_id)
            self.assertIsNotNone(change_set)
            self.assertEqual(change_set.status, "failed")

            conflict_row = db.get(MemoryEntity, "e_conflict")
            self.assertIsNone(conflict_row)


if __name__ == "__main__":
    unittest.main()
