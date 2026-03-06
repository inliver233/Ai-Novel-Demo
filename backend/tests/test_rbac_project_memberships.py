from __future__ import annotations

import unittest
from typing import Generator

from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import chapters as chapters_routes
from app.api.routes import projects as projects_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.project_settings import ProjectSettings
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
    app.include_router(projects_routes.router, prefix="/api")
    app.include_router(chapters_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestProjectMembershipRbac(unittest.TestCase):
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
                ProjectSettings.__table__,
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
                    User(id="u_out", display_name="out"),
                ]
            )
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(ProjectMembership(project_id="p1", user_id="u_editor", role="editor"))
            db.add(ProjectMembership(project_id="p1", user_id="u_viewer", role="viewer"))
            db.commit()

    def test_unauth_is_401(self) -> None:
        client = TestClient(self.app)
        resp = client.get("/api/projects")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "UNAUTHORIZED")

    def test_member_can_list_projects(self) -> None:
        client = TestClient(self.app)
        resp = client.get("/api/projects", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(resp.status_code, 200)
        projects = resp.json()["data"]["projects"]
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], "p1")

    def test_outsider_get_project_is_404(self) -> None:
        client = TestClient(self.app)
        resp = client.get("/api/projects/p1", headers={"X-Test-User": "u_out"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "NOT_FOUND")

    def test_viewer_cannot_create_chapter_but_can_read_after_editor_creates(self) -> None:
        client = TestClient(self.app)

        resp_forbidden = client.post(
            "/api/projects/p1/chapters",
            headers={"X-Test-User": "u_viewer"},
            json={"number": 1, "title": "Ch1"},
        )
        self.assertEqual(resp_forbidden.status_code, 403)

        resp_create = client.post(
            "/api/projects/p1/chapters",
            headers={"X-Test-User": "u_editor"},
            json={"number": 1, "title": "Ch1"},
        )
        self.assertEqual(resp_create.status_code, 200)

        resp_list = client.get("/api/projects/p1/chapters", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(resp_list.status_code, 200)
        chapters = resp_list.json()["data"]["chapters"]
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["number"], 1)

        resp_meta = client.get("/api/projects/p1/chapters/meta", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(resp_meta.status_code, 200)
        meta_chapters = resp_meta.json()["data"]["chapters"]
        self.assertEqual(len(meta_chapters), 1)
        self.assertEqual(meta_chapters[0]["number"], 1)
        self.assertNotIn("content_md", meta_chapters[0])

    def test_editor_cannot_delete_project(self) -> None:
        client = TestClient(self.app)
        resp = client.delete("/api/projects/p1", headers={"X-Test-User": "u_editor"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")

    def test_owner_can_delete_project(self) -> None:
        client = TestClient(self.app)
        resp = client.delete("/api/projects/p1", headers={"X-Test-User": "u_owner"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ok"], True)

    def test_invalid_role_cannot_be_written(self) -> None:
        with self.SessionLocal() as db:
            db.add(User(id="u_bad_role", display_name="bad_role"))
            db.commit()

            with self.assertRaises(Exception):
                db.add(ProjectMembership(project_id="p1", user_id="u_bad_role", role="hacker"))
                db.commit()
            db.rollback()

    def test_role_is_case_insensitive_and_trimmed(self) -> None:
        with self.SessionLocal() as db:
            db.add(User(id="u_editor_caps", display_name="editor_caps"))
            db.add(ProjectMembership(project_id="p1", user_id="u_editor_caps", role="  EDITOR  "))
            db.commit()

        client = TestClient(self.app)
        resp_create = client.post(
            "/api/projects/p1/chapters",
            headers={"X-Test-User": "u_editor_caps"},
            json={"number": 2, "title": "Ch2"},
        )
        self.assertEqual(resp_create.status_code, 200)


if __name__ == "__main__":
    unittest.main()
