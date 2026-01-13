from __future__ import annotations

import unittest
from typing import Generator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.api.routes import projects as projects_routes
from app.api.routes import writing_styles as writing_styles_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.outline import Outline
from app.models.project import Project
from app.models.user import User
from app.models.user_password import UserPassword
from app.models.writing_style import WritingStyle
from app.services.auth_service import hash_password


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

    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(projects_routes.router, prefix="/api")
    app.include_router(writing_styles_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestRequestSchemaFailClosedPhase1(unittest.TestCase):
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
                UserPassword.__table__,
                Project.__table__,
                Outline.__table__,
                WritingStyle.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.add(UserPassword(user_id="u1", password_hash=hash_password("password123"), disabled_at=None))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_auth_login_rejects_unknown_field(self) -> None:
        client = TestClient(self.app)

        ok = client.post("/api/auth/local/login", json={"user_id": "u1", "password": "password123"})
        self.assertEqual(ok.status_code, 200)

        bad = client.post("/api/auth/local/login", json={"user_id": "u1", "password": "password123", "extra": "x"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "VALIDATION_ERROR")

    def test_projects_update_rejects_unknown_field(self) -> None:
        client = TestClient(self.app)

        ok = client.put("/api/projects/p1", headers={"X-Test-User": "u1"}, json={"name": "Project 1 updated"})
        self.assertEqual(ok.status_code, 200)

        bad = client.put(
            "/api/projects/p1",
            headers={"X-Test-User": "u1"},
            json={"name": "Project 1 updated again", "extra": "x"},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "VALIDATION_ERROR")

    def test_writing_styles_create_rejects_unknown_field(self) -> None:
        client = TestClient(self.app)

        ok = client.post(
            "/api/writing_styles",
            headers={"X-Test-User": "u1"},
            json={"name": "Style 1", "prompt_content": "prompt"},
        )
        self.assertEqual(ok.status_code, 200)

        bad = client.post(
            "/api/writing_styles",
            headers={"X-Test-User": "u1"},
            json={"name": "Style 2", "prompt_content": "prompt", "extra": "x"},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
