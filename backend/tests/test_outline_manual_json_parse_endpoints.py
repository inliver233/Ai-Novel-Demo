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

from app.api.routes import outline as outline_routes
from app.api.routes import outlines as outlines_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.models.user import User


RAW_PAYLOAD = json.dumps(
    {
        "outline_md": "# 整体梗概\n- 手工粘贴的大纲应该被识别",
        "chapters": [
            {"number": 1, "title": "开篇", "beats": ["主角醒来", "系统出现"]},
            {"number": 2, "title": "立足", "beats": ["开始营业"]},
        ],
    },
    ensure_ascii=False,
    indent=2,
)


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
    app.include_router(outline_routes.router, prefix="/api")
    app.include_router(outlines_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestOutlineManualJsonParseEndpoints(unittest.TestCase):
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
                ProjectSettings.__table__,
                Outline.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(ProjectSettings(project_id="p1", vector_index_dirty=False, auto_update_tables_enabled=False))
            db.add(Outline(id="o1", project_id="p1", title="Outline 1", content_md="", structure_json=None))
            db.commit()

            project = db.get(Project, "p1")
            assert project is not None
            project.active_outline_id = "o1"
            db.commit()

    def test_put_outline_normalizes_manual_json_payload(self) -> None:
        client = TestClient(self.app)

        with patch("app.api.routes.outline.schedule_vector_rebuild_task", return_value=None), patch(
            "app.api.routes.outline.schedule_search_rebuild_task", return_value=None
        ):
            resp = client.put(
                "/api/projects/p1/outline",
                headers={"X-Test-User": "u_owner"},
                json={"content_md": RAW_PAYLOAD},
            )

        self.assertEqual(resp.status_code, 200)
        outline = (resp.json().get("data") or {}).get("outline") or {}
        self.assertEqual(str(outline.get("content_md") or "").strip(), "# 整体梗概\n- 手工粘贴的大纲应该被识别")
        chapters = ((outline.get("structure") or {}).get("chapters") or [])
        self.assertEqual(len(chapters), 2)

    def test_get_outline_derives_structure_from_legacy_raw_json_row(self) -> None:
        with self.SessionLocal() as db:
            row = db.get(Outline, "o1")
            assert row is not None
            row.content_md = RAW_PAYLOAD
            row.structure_json = None
            db.commit()

        client = TestClient(self.app)
        resp = client.get("/api/projects/p1/outline", headers={"X-Test-User": "u_owner"})

        self.assertEqual(resp.status_code, 200)
        outline = (resp.json().get("data") or {}).get("outline") or {}
        self.assertEqual(str(outline.get("content_md") or "").strip(), "# 整体梗概\n- 手工粘贴的大纲应该被识别")
        chapters = ((outline.get("structure") or {}).get("chapters") or [])
        self.assertEqual([item.get("number") for item in chapters], [1, 2])

    def test_create_outline_normalizes_manual_json_payload(self) -> None:
        client = TestClient(self.app)

        with patch("app.api.routes.outlines.schedule_vector_rebuild_task", return_value=None), patch(
            "app.api.routes.outlines.schedule_search_rebuild_task", return_value=None
        ):
            resp = client.post(
                "/api/projects/p1/outlines",
                headers={"X-Test-User": "u_owner"},
                json={"title": "Imported", "content_md": RAW_PAYLOAD},
            )

        self.assertEqual(resp.status_code, 200)
        outline = (resp.json().get("data") or {}).get("outline") or {}
        self.assertEqual(str(outline.get("content_md") or "").strip(), "# 整体梗概\n- 手工粘贴的大纲应该被识别")
        chapters = ((outline.get("structure") or {}).get("chapters") or [])
        self.assertEqual(len(chapters), 2)


if __name__ == "__main__":
    unittest.main()
