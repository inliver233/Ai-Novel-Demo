from __future__ import annotations

import json
import unittest
from typing import Generator

from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import settings as settings_routes
from app.core.config import settings
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
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
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(settings_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestSettingsApiKeyRedaction(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = settings.app_env
        self._old_key = settings.secret_encryption_key
        self.addCleanup(self._restore_settings)

        settings.app_env = "dev"
        settings.secret_encryption_key = Fernet.generate_key().decode("utf-8")

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
                ]
            )
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(ProjectMembership(project_id="p1", user_id="u_editor", role="editor"))
            db.commit()

    def _restore_settings(self) -> None:
        settings.app_env = self._old_env
        settings.secret_encryption_key = self._old_key

    def test_settings_api_never_returns_plain_api_key(self) -> None:
        client = TestClient(self.app)
        api_key = "sk-test-SECRET1234"

        put = client.put(
            "/api/projects/p1/settings",
            headers={"X-Test-User": "u_editor"},
            json={
                "vector_embedding_provider": "openai_compatible",
                "vector_embedding_base_url": "http://127.0.0.1:4010/v1",
                "vector_embedding_model": "text-embedding-mock",
                "vector_embedding_api_key": api_key,
                "vector_rerank_provider": "external_rerank_api",
                "vector_rerank_base_url": "http://127.0.0.1:4011",
                "vector_rerank_model": "rerank-mock",
                "vector_rerank_timeout_seconds": 15,
                "vector_rerank_hybrid_alpha": 0.25,
                "vector_rerank_api_key": api_key,
            },
        )
        self.assertEqual(put.status_code, 200)
        put_json = put.json()
        self.assertNotIn(api_key, json.dumps(put_json, ensure_ascii=False))

        settings_out = put_json["data"]["settings"]
        self.assertTrue(settings_out["vector_embedding_has_api_key"])
        self.assertEqual(settings_out["vector_embedding_masked_api_key"], "sk-****1234")
        self.assertNotIn("vector_embedding_api_key", settings_out)
        self.assertNotIn(api_key, str(settings_out.get("vector_embedding_effective_masked_api_key", "")))
        self.assertTrue(settings_out["vector_rerank_has_api_key"])
        self.assertEqual(settings_out["vector_rerank_masked_api_key"], "sk-****1234")
        self.assertNotIn("vector_rerank_api_key", settings_out)

        got = client.get("/api/projects/p1/settings", headers={"X-Test-User": "u_editor"})
        self.assertEqual(got.status_code, 200)
        got_json = got.json()
        self.assertNotIn(api_key, json.dumps(got_json, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
