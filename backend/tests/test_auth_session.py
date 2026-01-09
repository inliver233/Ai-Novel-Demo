from __future__ import annotations

import unittest
from datetime import timedelta
from typing import Generator

from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes.auth import router as auth_router
from app.core.auth_session import decode_session_cookie, encode_session_cookie
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_db
from app.db.utils import utc_now
from app.main import app_error_handler, auth_session_middleware
from app.models.user import User


def _make_test_app(SessionLocal: sessionmaker) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "rid-test"
        return await call_next(request)

    app.middleware("http")(auth_session_middleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(auth_router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestAuthSessionCookie(unittest.TestCase):
    def test_encode_decode_roundtrip(self) -> None:
        now = utc_now()
        value = encode_session_cookie(user_id="u1", expires_at=now + timedelta(seconds=123))
        session = decode_session_cookie(value, now=now)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.user_id, "u1")

    def test_decode_rejects_expired(self) -> None:
        now = utc_now()
        value = encode_session_cookie(user_id="u1", expires_at=now - timedelta(seconds=1))
        self.assertIsNone(decode_session_cookie(value, now=now))

    def test_decode_rejects_tampering(self) -> None:
        now = utc_now()
        value = encode_session_cookie(user_id="u1", expires_at=now + timedelta(seconds=60))
        parts = value.split(".")
        self.assertEqual(len(parts), 3)
        payload_b64 = parts[1]
        tampered_payload_b64 = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
        tampered = ".".join([parts[0], tampered_payload_b64, parts[2]])
        self.assertIsNone(decode_session_cookie(tampered, now=now))


class TestAuthEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        User.__table__.create(engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

    def test_auth_user_returns_401_when_not_logged_in(self) -> None:
        client = TestClient(self.app)
        resp = client.get("/api/auth/user")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "UNAUTHORIZED")

    def test_login_then_auth_user(self) -> None:
        client = TestClient(self.app)
        resp = client.post("/api/auth/local/login")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(client.cookies.get(settings.auth_cookie_user_id_name))
        self.assertIsNotNone(client.cookies.get(settings.auth_cookie_expire_at_name))

        resp2 = client.get("/api/auth/user")
        self.assertEqual(resp2.status_code, 200)
        data = resp2.json()["data"]
        self.assertEqual(data["user"]["id"], "local-user")
        self.assertIn("session", data)

    def test_refresh_extends_when_near_expiry(self) -> None:
        client = TestClient(self.app)
        now = utc_now()
        near_exp = now + timedelta(seconds=max(1, settings.auth_refresh_threshold_seconds - 1))
        client.cookies.set(settings.auth_cookie_user_id_name, encode_session_cookie(user_id="u1", expires_at=near_exp))

        resp = client.post("/api/auth/refresh")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()["data"]
        self.assertTrue(payload["refreshed"])
        self.assertGreater(payload["session"]["expire_at"], int(near_exp.timestamp()))


if __name__ == "__main__":
    unittest.main()
