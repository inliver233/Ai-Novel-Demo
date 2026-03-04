from __future__ import annotations

import unittest

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.secrets import encrypt_secret
from app.db.base import Base
from app.models.llm_preset import LLMPreset
from app.models.llm_profile import LLMProfile
from app.models.llm_task_preset import LLMTaskPreset
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.user import User
from app.services.llm_task_preset_resolver import resolve_task_llm_config, resolve_task_preset


class TestLlmTaskPresetResolver(unittest.TestCase):
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
                LLMPreset.__table__,
                LLMTaskPreset.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", llm_profile_id="prof-main"))
            db.add(
                LLMProfile(
                    id="prof-main",
                    owner_user_id="u_owner",
                    name="main",
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                    api_key_ciphertext=encrypt_secret("sk-main-123"),
                    api_key_masked="sk-****123",
                )
            )
            db.add(
                LLMProfile(
                    id="prof-task",
                    owner_user_id="u_owner",
                    name="task",
                    provider="anthropic",
                    base_url="https://api.anthropic.com",
                    model="claude-3-7-sonnet-20250219",
                    api_key_ciphertext=encrypt_secret("sk-task-456"),
                    api_key_masked="sk-****456",
                )
            )
            db.add(
                LLMPreset(
                    project_id="p1",
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                    temperature=0.7,
                    top_p=1.0,
                    max_tokens=12000,
                    presence_penalty=0.0,
                    frequency_penalty=0.0,
                    top_k=None,
                    stop_json="[]",
                    timeout_seconds=180,
                    extra_json="{}",
                )
            )
            db.add(
                LLMTaskPreset(
                    project_id="p1",
                    task_key="chapter_generate",
                    llm_profile_id="prof-task",
                    provider="anthropic",
                    base_url="https://api.anthropic.com",
                    model="claude-3-7-sonnet-20250219",
                    temperature=0.3,
                    top_p=0.9,
                    max_tokens=4096,
                    top_k=40,
                    stop_json="[]",
                    timeout_seconds=120,
                    extra_json='{"thinking":{"type":"enabled","budget_tokens":512}}',
                )
            )
            db.commit()

    def _restore_settings(self) -> None:
        settings.secret_encryption_key = self._old_secret_key

    def test_resolve_task_preset_prefers_task_override(self) -> None:
        with self.SessionLocal() as db:
            row, source = resolve_task_preset(db, project_id="p1", task_key="chapter_generate")
            self.assertIsNotNone(row)
            self.assertEqual(source, "task_override")
            self.assertEqual(getattr(row, "provider"), "anthropic")

    def test_resolve_task_preset_falls_back_to_project_default(self) -> None:
        with self.SessionLocal() as db:
            row, source = resolve_task_preset(db, project_id="p1", task_key="outline_generate")
            self.assertIsNotNone(row)
            self.assertEqual(source, "project_default")
            self.assertEqual(getattr(row, "provider"), "openai")

    def test_resolve_task_llm_config_uses_task_profile_key(self) -> None:
        with self.SessionLocal() as db:
            project = db.get(Project, "p1")
            self.assertIsNotNone(project)
            resolved = resolve_task_llm_config(
                db,
                project=project,  # type: ignore[arg-type]
                user_id="u_owner",
                task_key="chapter_generate",
                header_api_key=None,
            )
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.source, "task_override")
            self.assertEqual(resolved.llm_call.provider, "anthropic")
            self.assertEqual(resolved.api_key, "sk-task-456")

    def test_resolve_task_llm_config_uses_project_profile_for_fallback(self) -> None:
        with self.SessionLocal() as db:
            project = db.get(Project, "p1")
            self.assertIsNotNone(project)
            resolved = resolve_task_llm_config(
                db,
                project=project,  # type: ignore[arg-type]
                user_id="u_owner",
                task_key="outline_generate",
                header_api_key=None,
            )
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.source, "project_default")
            self.assertEqual(resolved.llm_call.provider, "openai")
            self.assertEqual(resolved.api_key, "sk-main-123")

    def test_header_api_key_overrides_profile_key(self) -> None:
        with self.SessionLocal() as db:
            project = db.get(Project, "p1")
            self.assertIsNotNone(project)
            resolved = resolve_task_llm_config(
                db,
                project=project,  # type: ignore[arg-type]
                user_id="u_owner",
                task_key="chapter_generate",
                header_api_key="sk-header-override",
            )
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.api_key, "sk-header-override")


if __name__ == "__main__":
    unittest.main()
