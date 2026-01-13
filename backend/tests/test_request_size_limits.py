from __future__ import annotations

import unittest
from typing import Generator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import llm_preset as llm_preset_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.models.user import User
from app.schemas.limits import MAX_JSON_CHARS_SMALL


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
    app.include_router(llm_preset_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestRequestSizeLimits(unittest.TestCase):
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
                LLMPreset.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_llm_preset_extra_rejects_oversize_json(self) -> None:
        client = TestClient(self.app)

        ok = client.put(
            "/api/projects/p1/llm_preset",
            headers={"X-Test-User": "u1"},
            json={"provider": "openai", "model": "gpt-4o-mini", "extra": {"k": "v"}},
        )
        self.assertEqual(ok.status_code, 200)

        too_large_value = "x" * (MAX_JSON_CHARS_SMALL + 100)
        bad = client.put(
            "/api/projects/p1/llm_preset",
            headers={"X-Test-User": "u1"},
            json={"provider": "openai", "model": "gpt-4o-mini", "extra": {"k": too_large_value}},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "VALIDATION_ERROR")

        errors = bad.json()["error"]["details"]["errors"]
        self.assertTrue(any(e.get("loc") == ["body", "extra"] for e in errors))


if __name__ == "__main__":
    unittest.main()
