from __future__ import annotations

import unittest
from typing import Generator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import llm_capabilities as llm_capabilities_routes
from app.api.routes import llm_preset as llm_preset_routes
from app.api.routes import llm_profiles as llm_profiles_routes
from app.api.routes import llm_task_presets as llm_task_presets_routes
from app.api.routes import projects as projects_routes
from app.core.config import settings
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.llm_preset import LLMPreset
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
    app.include_router(llm_capabilities_routes.router, prefix="/api")
    app.include_router(llm_profiles_routes.router, prefix="/api")
    app.include_router(projects_routes.router, prefix="/api")
    app.include_router(llm_preset_routes.router, prefix="/api")
    app.include_router(llm_task_presets_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestLlmContractRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._old_contract_mode = settings.llm_config_mode
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
                LLMPreset.__table__,
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
            db.commit()

    def _restore_settings(self) -> None:
        settings.llm_config_mode = self._old_contract_mode

    def test_llm_capabilities_canonicalizes_alias_model(self) -> None:
        res = self.client.get(
            "/api/llm_capabilities?provider=openai&model=gpt-4o-mini-2024-07-18",
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["data"]["capabilities"]
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["model_key"], "openai::gpt-4o-mini")
        self.assertTrue(payload["known_model"])

    def test_enforce_rejects_unknown_official_model_on_profile_create(self) -> None:
        settings.llm_config_mode = "enforce"
        res = self.client.post(
            "/api/llm_profiles",
            headers=self.headers,
            json={
                "name": "Strict OpenAI",
                "provider": "openai",
                "model": "gpt-lab-preview-x",
            },
        )
        self.assertEqual(res.status_code, 400)
        payload = res.json()
        error = payload.get("error") or {}
        self.assertEqual(error.get("code"), "LLM_CONFIG_ERROR")
        self.assertEqual((error.get("details") or {}).get("contract_code"), "unsupported_model")

    def test_put_preset_canonicalizes_alias_model(self) -> None:
        res = self.client.put(
            "/api/projects/p1/llm_preset",
            headers=self.headers,
            json={
                "provider": "openai",
                "base_url": None,
                "model": "gpt-4o-mini-2024-07-18",
                "temperature": 0.7,
                "top_p": 1.0,
                "max_tokens": 20000,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "top_k": None,
                "stop": [],
                "timeout_seconds": 180,
                "extra": {},
            },
        )
        self.assertEqual(res.status_code, 200)
        preset = res.json()["data"]["llm_preset"]
        self.assertEqual(preset["provider"], "openai")
        self.assertEqual(preset["model"], "gpt-4o-mini")
        self.assertEqual(preset["model_key"], "openai::gpt-4o-mini")
        self.assertEqual(preset["max_tokens"], 16384)

        with self.SessionLocal() as db:
            row = db.get(LLMPreset, "p1")
            self.assertIsNotNone(row)
            self.assertEqual(row.provider, "openai")
            self.assertEqual(row.model, "gpt-4o-mini")

    def test_enforce_keeps_gateway_passthrough_for_openai_compatible(self) -> None:
        settings.llm_config_mode = "enforce"
        res = self.client.put(
            "/api/projects/p1/llm_task_presets/chapter_generate",
            headers=self.headers,
            json={
                "llm_profile_id": None,
                "provider": "openai_compatible",
                "base_url": "https://gateway.example/v1",
                "model": "custom-gateway-model",
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": 4096,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "top_k": None,
                "stop": [],
                "timeout_seconds": 120,
                "extra": {},
            },
        )
        self.assertEqual(res.status_code, 200)
        task = res.json()["data"]["task_preset"]
        self.assertEqual(task["provider"], "openai_compatible")
        self.assertEqual(task["model"], "custom-gateway-model")
        self.assertFalse(task["known_model"])
        self.assertEqual(task["contract_mode"], "enforce")


if __name__ == "__main__":
    unittest.main()
