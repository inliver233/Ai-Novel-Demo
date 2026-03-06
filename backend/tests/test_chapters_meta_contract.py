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


class TestChapterMetaContract(unittest.TestCase):
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
                ]
            )
            project = Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None)
            outline = Outline(id="o1", project_id="p1", title="Outline 1", content_md="# Outline")
            project.active_outline_id = outline.id
            db.add(project)
            db.add(outline)
            db.add(ProjectMembership(project_id="p1", user_id="u_editor", role="editor"))
            db.add(ProjectMembership(project_id="p1", user_id="u_viewer", role="viewer"))
            db.commit()

    def test_meta_list_omits_fulltext_fields_and_supports_cursor(self) -> None:
        with self.SessionLocal() as db:
            db.add_all(
                [
                    Chapter(
                        id="c1",
                        project_id="p1",
                        outline_id="o1",
                        number=1,
                        title="Chapter 1",
                        plan="Plan 1",
                        content_md="# C1",
                        summary="Summary 1",
                        status="done",
                    ),
                    Chapter(
                        id="c2",
                        project_id="p1",
                        outline_id="o1",
                        number=2,
                        title="Chapter 2",
                        plan=None,
                        content_md=None,
                        summary=None,
                        status="planned",
                    ),
                ]
            )
            db.commit()

        client = TestClient(self.app)
        first = client.get("/api/projects/p1/chapters/meta?limit=1", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(first.status_code, 200)
        first_json = first.json()["data"]
        self.assertEqual(first_json["returned"], 1)
        self.assertEqual(first_json["total"], 2)
        self.assertTrue(first_json["has_more"])
        self.assertEqual(first_json["next_cursor"], 1)
        chapter = first_json["chapters"][0]
        self.assertEqual(chapter["id"], "c1")
        self.assertTrue(chapter["has_plan"])
        self.assertTrue(chapter["has_summary"])
        self.assertTrue(chapter["has_content"])
        self.assertNotIn("plan", chapter)
        self.assertNotIn("summary", chapter)
        self.assertNotIn("content_md", chapter)

        second = client.get("/api/projects/p1/chapters/meta?limit=1&cursor=1", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(second.status_code, 200)
        second_json = second.json()["data"]
        self.assertEqual(second_json["returned"], 1)
        self.assertEqual(second_json["total"], 2)
        self.assertFalse(second_json["has_more"])
        self.assertIsNone(second_json["next_cursor"])
        chapter2 = second_json["chapters"][0]
        self.assertEqual(chapter2["id"], "c2")
        self.assertFalse(chapter2["has_plan"])
        self.assertFalse(chapter2["has_summary"])
        self.assertFalse(chapter2["has_content"])

    def test_legacy_list_and_detail_keep_full_payload(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                Chapter(
                    id="c1",
                    project_id="p1",
                    outline_id="o1",
                    number=1,
                    title="Chapter 1",
                    plan="Plan 1",
                    content_md="# C1",
                    summary="Summary 1",
                    status="done",
                )
            )
            db.commit()

        client = TestClient(self.app)

        legacy = client.get("/api/projects/p1/chapters", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(legacy.status_code, 200)
        legacy_chapter = legacy.json()["data"]["chapters"][0]
        self.assertEqual(legacy_chapter["plan"], "Plan 1")
        self.assertEqual(legacy_chapter["summary"], "Summary 1")
        self.assertEqual(legacy_chapter["content_md"], "# C1")

        detail = client.get("/api/chapters/c1", headers={"X-Test-User": "u_viewer"})
        self.assertEqual(detail.status_code, 200)
        detail_chapter = detail.json()["data"]["chapter"]
        self.assertEqual(detail_chapter["plan"], "Plan 1")
        self.assertEqual(detail_chapter["summary"], "Summary 1")
        self.assertEqual(detail_chapter["content_md"], "# C1")


if __name__ == "__main__":
    unittest.main()
