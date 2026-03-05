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
from app.core.errors import AppError
from app.db.session import get_db
from app.db.utils import utc_now
from app.main import app_error_handler, auth_session_middleware
from app.models.user import User
from app.models.user_activity_stat import UserActivityStat
from app.models.user_password import UserPassword
from app.models.user_usage_stat import UserUsageStat
from app.services.auth_service import hash_password


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


class TestAdminUserStats(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        User.__table__.create(engine)
        UserPassword.__table__.create(engine)
        UserActivityStat.__table__.create(engine)
        UserUsageStat.__table__.create(engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        self._seed_user("admin", "admin-password-123", is_admin=True)
        self._seed_user("u1", "password-123")
        self._seed_user("u2", "password-123")

        now = utc_now()
        with self.SessionLocal() as db:
            db.add(
                UserActivityStat(
                    user_id="u1",
                    last_seen_at=now - timedelta(seconds=60),
                    last_seen_request_id="rid-u1",
                    last_seen_path="/api/projects",
                    last_seen_method="GET",
                    last_seen_status=200,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                UserActivityStat(
                    user_id="u2",
                    last_seen_at=now - timedelta(hours=2),
                    last_seen_request_id="rid-u2",
                    last_seen_path="/api/projects",
                    last_seen_method="GET",
                    last_seen_status=200,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                UserUsageStat(
                    user_id="u1",
                    total_generation_calls=10,
                    total_generation_error_calls=2,
                    total_generated_chars=5000,
                    last_generation_at=now - timedelta(minutes=5),
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                UserUsageStat(
                    user_id="u2",
                    total_generation_calls=3,
                    total_generation_error_calls=0,
                    total_generated_chars=1200,
                    last_generation_at=now - timedelta(hours=1),
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

    def _seed_user(self, user_id: str, password: str, *, is_admin: bool = False) -> None:
        with self.SessionLocal() as db:
            db.add(User(id=user_id, display_name=user_id, is_admin=is_admin))
            db.add(
                UserPassword(
                    user_id=user_id,
                    password_hash=hash_password(password),
                    disabled_at=None,
                )
            )
            db.commit()

    def _login_as_admin(self, client: TestClient) -> None:
        resp = client.post("/api/auth/local/login", json={"user_id": "admin", "password": "admin-password-123"})
        self.assertEqual(resp.status_code, 200)

    def test_admin_users_endpoint_returns_summary_and_stats(self) -> None:
        client = TestClient(self.app)
        self._login_as_admin(client)

        resp = client.get("/api/auth/admin/users?limit=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertIn("users", data)
        self.assertIn("summary", data)
        self.assertIn("pagination", data)

        summary = data["summary"]
        self.assertEqual(summary["total_users"], 3)
        self.assertEqual(summary["total_admin_users"], 1)
        self.assertEqual(summary["total_online_users"], 1)
        self.assertEqual(summary["total_generation_calls"], 13)
        self.assertEqual(summary["total_generated_chars"], 6200)

        users = data["users"]
        self.assertGreaterEqual(len(users), 1)
        first = users[0]
        self.assertIn("activity", first)
        self.assertIn("usage", first)
        self.assertIn("online", first["activity"])
        self.assertIn("total_generation_calls", first["usage"])

    def test_admin_users_endpoint_supports_online_only_and_pagination(self) -> None:
        client = TestClient(self.app)
        self._login_as_admin(client)

        online_only = client.get("/api/auth/admin/users?online_only=true&limit=5")
        self.assertEqual(online_only.status_code, 200)
        online_users = online_only.json()["data"]["users"]
        self.assertEqual(len(online_users), 1)
        self.assertEqual(online_users[0]["id"], "u1")
        self.assertTrue(online_users[0]["activity"]["online"])

        first_page = client.get("/api/auth/admin/users?limit=1")
        self.assertEqual(first_page.status_code, 200)
        first_payload = first_page.json()["data"]
        self.assertTrue(first_payload["pagination"]["has_more"])
        next_cursor = first_payload["pagination"]["next_cursor"]
        self.assertTrue(isinstance(next_cursor, str) and len(next_cursor) > 0)

        second_page = client.get(f"/api/auth/admin/users?limit=1&cursor={next_cursor}")
        self.assertEqual(second_page.status_code, 200)
        second_payload = second_page.json()["data"]
        self.assertEqual(len(second_payload["users"]), 1)
        self.assertNotEqual(first_payload["users"][0]["id"], second_payload["users"][0]["id"])


if __name__ == "__main__":
    unittest.main()
