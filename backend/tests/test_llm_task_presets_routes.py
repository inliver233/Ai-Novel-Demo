from __future__ import annotations

import unittest
from typing import Generator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import llm_task_presets as llm_task_presets_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.llm_profile import LLMProfile
from app.models.llm_task_preset import LLMTaskPreset
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
    app.include_router(llm_task_presets_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestLlmTaskPresetsRoutes(unittest.TestCase):
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
                ProjectMembership.__table__,
                LLMProfile.__table__,
                LLMTaskPreset.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)
        self.client = TestClient(self.app)
        self.headers = {"X-Test-User": "u_owner"}

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(
                LLMProfile(
                    id="prof-openai",
                    owner_user_id="u_owner",
                    name="OpenAI",
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                )
            )
            db.add(
                LLMProfile(
                    id="prof-anthropic",
                    owner_user_id="u_owner",
                    name="Claude",
                    provider="anthropic",
                    base_url="https://api.anthropic.com",
                    model="claude-3-7-sonnet-20250219",
                )
            )
            db.commit()

    def test_list_empty_and_catalog_available(self) -> None:
        res = self.client.get("/api/projects/p1/llm_task_presets", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertIsInstance(data.get("catalog"), list)
        self.assertGreater(len(data.get("catalog") or []), 0)
        self.assertEqual(data.get("task_presets"), [])

    def test_put_rejects_profile_provider_mismatch(self) -> None:
        res = self.client.put(
            "/api/projects/p1/llm_task_presets/chapter_generate",
            headers=self.headers,
            json={
                "llm_profile_id": "prof-openai",
                "provider": "anthropic",
                "base_url": "https://api.anthropic.com",
                "model": "claude-3-7-sonnet-20250219",
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": 2048,
                "stop": [],
                "extra": {},
            },
        )
        self.assertEqual(res.status_code, 400)
        payload = res.json()
        code = payload.get("code") or (payload.get("error") or {}).get("code")
        self.assertEqual(code, "LLM_CONFIG_ERROR")

    def test_put_and_delete_task_preset(self) -> None:
        put = self.client.put(
            "/api/projects/p1/llm_task_presets/chapter_generate",
            headers=self.headers,
            json={
                "llm_profile_id": "prof-openai",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "temperature": 0.3,
                "top_p": 0.95,
                "max_tokens": 4096,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "top_k": None,
                "stop": ["###"],
                "timeout_seconds": 120,
                "extra": {"reasoning_effort": "low"},
            },
        )
        self.assertEqual(put.status_code, 200)
        task = put.json()["data"]["task_preset"]
        self.assertEqual(task["task_key"], "chapter_generate")
        self.assertEqual(task["llm_profile_id"], "prof-openai")
        self.assertEqual(task["provider"], "openai")
        self.assertEqual(task["model"], "gpt-4o-mini")
        self.assertEqual(task["stop"], ["###"])

        listed = self.client.get("/api/projects/p1/llm_task_presets", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        rows = listed.json()["data"]["task_presets"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["task_key"], "chapter_generate")

        deleted = self.client.delete("/api/projects/p1/llm_task_presets/chapter_generate", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)

        listed2 = self.client.get("/api/projects/p1/llm_task_presets", headers=self.headers)
        self.assertEqual(listed2.status_code, 200)
        self.assertEqual(listed2.json()["data"]["task_presets"], [])


if __name__ == "__main__":
    unittest.main()
