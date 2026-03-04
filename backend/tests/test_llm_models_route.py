from __future__ import annotations

import json
import unittest
from typing import Generator
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import llm_models as llm_models_routes
from app.core.config import settings
from app.core.errors import AppError
from app.core.secrets import encrypt_secret
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.llm_profile import LLMProfile
from app.models.project import Project
from app.models.project_membership import ProjectMembership
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
    app.include_router(llm_models_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestLlmModelsRoute(unittest.TestCase):
    def setUp(self) -> None:
        self._old_secret_key = settings.secret_encryption_key
        settings.secret_encryption_key = Fernet.generate_key().decode("utf-8")
        self.addCleanup(self._restore_settings)

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
                LLMProfile.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)
        self.client = TestClient(self.app)
        self.headers = {"X-Test-User": "u_owner"}

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", llm_profile_id="prof1"))
            db.add(Project(id="p2", owner_user_id="u_owner", name="Project 2", llm_profile_id=None))
            db.add(
                LLMProfile(
                    id="prof1",
                    owner_user_id="u_owner",
                    name="Proxy",
                    provider="openai_compatible",
                    base_url="http://stubbed-openai.local/proxy",
                    model="gpt-test",
                    api_key_ciphertext=encrypt_secret("sk-test-123"),
                    api_key_masked="sk-****123",
                )
            )
            db.commit()

    def _restore_settings(self) -> None:
        settings.secret_encryption_key = self._old_secret_key

    def test_openai_compatible_models_support_v1_fallback_and_dedupe(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            self.assertEqual(request.headers.get("Authorization"), "Bearer sk-test-123")
            if request.url.path.endswith("/proxy/models"):
                return httpx.Response(404, json={"error": {"message": "not found"}})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "gpt-test", "name": "GPT Test"},
                        {"id": "gpt-test", "name": "GPT Test Dup"},
                        {"id": "gpt-lite", "name": "GPT Lite"},
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as http_client:
            with patch("app.api.routes.llm_models.get_llm_http_client", return_value=http_client):
                res = self.client.get(
                    "/api/llm_models?provider=openai_compatible&base_url=http%3A%2F%2Fstubbed-openai.local%2Fproxy&profile_id=prof1",
                    headers=self.headers,
                )

        self.assertEqual(res.status_code, 200)
        payload = res.json()["data"]
        models = payload["models"]
        self.assertEqual([m["id"] for m in models], ["gpt-lite", "gpt-test"])
        self.assertIsNone(payload.get("warning"))
        self.assertEqual(seen_paths[0], "/proxy/models")
        self.assertEqual(seen_paths[-1], "/proxy/v1/models")

    def test_returns_warning_when_project_has_no_api_key(self) -> None:
        res = self.client.get("/api/llm_models?provider=openai&project_id=p2", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()["data"]
        self.assertEqual(payload["models"], [])
        warning = payload.get("warning") or {}
        self.assertEqual(warning.get("code"), "LLM_KEY_MISSING")


if __name__ == "__main__":
    unittest.main()
