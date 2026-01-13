from __future__ import annotations

import json
import unittest
from typing import Generator
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import llm_profiles as llm_profiles_routes
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import exception_log_fields
from app.core.secrets import mask_api_key
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.llm_profile import LLMProfile
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

    app.include_router(llm_profiles_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestSecretsRedaction(unittest.TestCase):
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
        Base.metadata.create_all(engine, tables=[User.__table__, LLMProfile.__table__])
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.commit()

    def _restore_settings(self) -> None:
        settings.app_env = self._old_env
        settings.secret_encryption_key = self._old_key

    def test_mask_api_key_handles_common_prefixes(self) -> None:
        self.assertEqual(mask_api_key("sk-test-SECRET1234"), "sk-****1234")
        self.assertEqual(mask_api_key("rk-test-SECRET9876"), "rk-****9876")
        self.assertEqual(mask_api_key("pk-test-SECRET0000"), "pk-****0000")
        self.assertEqual(mask_api_key("AIzaSyDUMMY1234567890"), "****7890")
        self.assertEqual(mask_api_key(""), "")
        self.assertEqual(mask_api_key("   "), "")

    def test_exception_log_fields_redacts_common_secret_patterns(self) -> None:
        msg = (
            "boom "
            "https://example.com?key=AIzaSyDUMMY1234567890&api_key=sk-test-SECRET1234&token=rk-test-SECRET9876 "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
            "X-LLM-API-Key: pk-test-SECRET0000 "
            "raw_tokens sk-test-SECRET1234 rk-test-SECRET9876 pk-test-SECRET0000 "
            "raw_google=AIzaSyDUMMY1234567890"
        )
        exc = ValueError(msg)

        with patch.object(settings, "app_env", "dev"):
            fields = exception_log_fields(exc)

        redacted = str(fields.get("exception") or "")
        self.assertIn("key=****", redacted)
        self.assertIn("api_key=****", redacted)
        self.assertIn("token=****", redacted)
        self.assertIn("Bearer ***", redacted)
        self.assertIn("X-LLM-API-Key: ***", redacted)
        self.assertIn("raw_google=AIza***", redacted)
        self.assertIn("sk-****1234", redacted)
        self.assertIn("rk-****9876", redacted)
        self.assertIn("pk-****0000", redacted)

        self.assertNotIn("sk-test-SECRET1234", redacted)
        self.assertNotIn("rk-test-SECRET9876", redacted)
        self.assertNotIn("pk-test-SECRET0000", redacted)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", redacted)
        self.assertNotIn("AIzaSyDUMMY1234567890", redacted)

    def test_llm_profile_api_never_returns_plain_api_key(self) -> None:
        client = TestClient(self.app)
        api_key = "sk-test-SECRET1234"

        create = client.post(
            "/api/llm_profiles",
            headers={"X-Test-User": "u1"},
            json={"name": "p1", "provider": "openai", "model": "gpt-4o-mini", "api_key": api_key},
        )
        self.assertEqual(create.status_code, 200)
        create_json = create.json()
        profile = create_json["data"]["profile"]
        self.assertTrue(profile["has_api_key"])
        self.assertEqual(profile["masked_api_key"], "sk-****1234")
        self.assertNotIn("api_key", profile)
        self.assertNotIn("api_key_ciphertext", profile)
        self.assertNotIn("api_key_masked", profile)
        self.assertNotIn(api_key, json.dumps(create_json, ensure_ascii=False))

        listed = client.get("/api/llm_profiles", headers={"X-Test-User": "u1"})
        self.assertEqual(listed.status_code, 200)
        listed_json = listed.json()
        profiles = listed_json["data"]["profiles"]
        self.assertEqual(len(profiles), 1)
        listed_profile = profiles[0]
        self.assertTrue(listed_profile["has_api_key"])
        self.assertEqual(listed_profile["masked_api_key"], "sk-****1234")
        self.assertNotIn("api_key", listed_profile)
        self.assertNotIn("api_key_ciphertext", listed_profile)
        self.assertNotIn("api_key_masked", listed_profile)
        self.assertNotIn(api_key, json.dumps(listed_json, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
