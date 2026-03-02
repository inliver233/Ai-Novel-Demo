from __future__ import annotations

import json
import unittest
from typing import Generator
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes import memory as memory_routes
from app.core.errors import AppError
from app.db.base import Base
from app.db.session import get_db
from app.main import app_error_handler, validation_error_handler
from app.models.llm_profile import LLMProfile
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.user import User
from app.models.worldbook_entry import WorldBookEntry
from app.services.memory_retrieval_service import retrieve_memory_context_pack


def _collect_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        out = set()
        for k, v in value.items():
            out.add(str(k))
            out |= _collect_keys(v)
        return out
    if isinstance(value, list):
        out = set()
        for item in value:
            out |= _collect_keys(item)
        return out
    return set()


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
    app.include_router(memory_routes.router, prefix="/api")

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


class TestMemoryPreviewEndpoints(unittest.TestCase):
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
                LLMProfile.__table__,
                Outline.__table__,
                Project.__table__,
                ProjectSettings.__table__,
                ProjectTable.__table__,
                ProjectTableRow.__table__,
                WorldBookEntry.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.app = _make_test_app(self.SessionLocal)

        with self.SessionLocal() as db:
            db.add(User(id="u_owner", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u_owner", name="Project 1", genre=None, logline=None))
            db.add(
                WorldBookEntry(
                    id="wb1",
                    project_id="p1",
                    title="Const Entry",
                    content_md="A" * 5000,
                    enabled=True,
                    constant=True,
                    keywords_json=None,
                    exclude_recursion=False,
                    prevent_recursion=False,
                    char_limit=20000,
                    priority="important",
                )
            )
            db.commit()

    def test_memory_preview_accepts_modules_and_budget_overrides(self) -> None:
        client = TestClient(self.app)
        resp = client.post(
            "/api/projects/p1/memory/preview",
            headers={"X-Test-User": "u_owner"},
            json={
                "query_text": "hello",
                "section_enabled": {
                    "worldbook": True,
                    "story_memory": False,
                    "structured": False,
                    "vector_rag": False,
                    "graph": False,
                    "fractal": False,
                },
                "budget_overrides": {
                    "worldbook": 200,
                    "story_memory": 300,
                    "structured": 400,
                    "vector_rag": 500,
                    "graph": 600,
                    "fractal": 700,
                    "unknown": 800,
                },
            },
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))

        data = payload.get("data") or {}
        self.assertIn("worldbook", data)
        self.assertIn("logs", data)

        worldbook = data["worldbook"]
        self.assertTrue(worldbook.get("enabled") is True)
        self.assertTrue(worldbook.get("truncated") is True)
        text_md = str(worldbook.get("text_md") or "")
        self.assertTrue(text_md.startswith("<WORLD_BOOK>\n"))
        self.assertTrue(text_md.endswith("\n</WORLD_BOOK>"))

        inner = text_md[len("<WORLD_BOOK>\n") : -len("\n</WORLD_BOOK>")]
        self.assertLessEqual(len(inner), 200)

        story_memory = data["story_memory"]
        self.assertEqual(story_memory.get("enabled"), False)
        self.assertEqual(story_memory.get("disabled_reason"), "disabled")

        logs = data["logs"]
        worldbook_log = next((x for x in logs if isinstance(x, dict) and x.get("section") == "worldbook"), None)
        self.assertIsNotNone(worldbook_log)
        self.assertEqual(worldbook_log.get("budget_char_limit"), 200)
        self.assertEqual(worldbook_log.get("budget_source"), "override")
        graph_log = next((x for x in logs if isinstance(x, dict) and x.get("section") == "graph"), None)
        self.assertIsNotNone(graph_log)
        graph_budget_obs = (graph_log or {}).get("budget_observability") if isinstance(graph_log, dict) else None
        self.assertIsInstance(graph_budget_obs, dict)
        self.assertEqual((graph_budget_obs or {}).get("module"), "graph")

    def test_memory_preview_tables_section_empty_when_no_tables(self) -> None:
        client = TestClient(self.app)
        resp = client.post(
            "/api/projects/p1/memory/preview",
            headers={"X-Test-User": "u_owner"},
            json={
                "query_text": "hello",
                "section_enabled": {
                    "worldbook": False,
                    "story_memory": False,
                    "structured": False,
                    "vector_rag": False,
                    "graph": False,
                    "fractal": False,
                    "tables": True,
                },
                "budget_overrides": {"tables": 200},
            },
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))

        data = payload.get("data") or {}
        tables = data.get("tables") or {}
        self.assertEqual(tables.get("enabled"), False)
        self.assertEqual(tables.get("disabled_reason"), "empty")
        self.assertEqual((tables.get("counts") or {}).get("tables"), 0)
        self.assertEqual((tables.get("counts") or {}).get("rows"), 0)
        self.assertEqual(str(tables.get("text_md") or ""), "")

    def test_memory_preview_tables_section_formats_text_and_respects_budget(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                ProjectTable(
                    id="t1",
                    project_id="p1",
                    table_key="money",
                    name="Money",
                    schema_version=1,
                    schema_json=json.dumps(
                        {
                            "version": 1,
                            "columns": [
                                {"key": "key", "type": "string", "label": "Key", "required": True},
                                {"key": "value", "type": "string", "label": "Value", "required": False},
                            ],
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            db.add(
                ProjectTableRow(
                    id="r1",
                    project_id="p1",
                    table_id="t1",
                    row_index=0,
                    data_json=json.dumps({"key": "gold", "value": "100"}, ensure_ascii=False),
                )
            )
            db.add(
                ProjectTableRow(
                    id="r2",
                    project_id="p1",
                    table_id="t1",
                    row_index=1,
                    data_json=json.dumps({"key": "gem", "value": "2"}, ensure_ascii=False),
                )
            )
            db.commit()

        client = TestClient(self.app)
        resp = client.post(
            "/api/projects/p1/memory/preview",
            headers={"X-Test-User": "u_owner"},
            json={
                "query_text": "gold",
                "section_enabled": {
                    "worldbook": False,
                    "story_memory": False,
                    "structured": False,
                    "vector_rag": False,
                    "graph": False,
                    "fractal": False,
                    "tables": True,
                },
                "budget_overrides": {"tables": 120},
            },
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))

        data = payload.get("data") or {}
        tables = data.get("tables") or {}
        self.assertEqual(tables.get("disabled_reason"), None)

        counts = tables.get("counts") or {}
        self.assertEqual(counts.get("tables"), 1)
        self.assertGreaterEqual(int(counts.get("rows") or 0), 1)

        text_md = str(tables.get("text_md") or "")
        self.assertTrue(text_md.startswith("<TABLES>\n"))
        self.assertTrue(text_md.endswith("\n</TABLES>") or text_md.endswith("</TABLES>"))
        self.assertLessEqual(len(text_md), 120)

    def test_retrieve_memory_context_pack_never_returns_plain_api_key(self) -> None:
        secret = "sk-test-SECRET1234"
        with self.SessionLocal() as db:
            db.add(ProjectSettings(project_id="p1", vector_embedding_api_key_ciphertext=secret))
            db.commit()

            def _fake_vector_status(*, project_id: str, embedding: dict, rerank: dict) -> dict:
                return {
                    "enabled": True,
                    "disabled_reason": None,
                    "embedding": embedding,
                    "api_key": embedding.get("api_key"),
                }

            with patch("app.services.memory_retrieval_service.vector_rag_status", side_effect=_fake_vector_status):
                pack = retrieve_memory_context_pack(
                    db=db,
                    project_id="p1",
                    query_text="hello",
                    section_enabled={
                        "worldbook": False,
                        "story_memory": False,
                        "structured": False,
                        "vector_rag": False,
                        "graph": False,
                        "fractal": False,
                    },
                )
                data = pack.model_dump()

        keys = _collect_keys(data)
        self.assertNotIn("api_key", keys)
        self.assertNotIn(secret, json.dumps(data, ensure_ascii=False))

    def test_memory_preview_api_never_returns_plain_api_key(self) -> None:
        secret = "sk-test-SECRET1234"
        with self.SessionLocal() as db:
            db.add(ProjectSettings(project_id="p1", vector_embedding_api_key_ciphertext=secret))
            db.commit()

        def _fake_vector_status(*, project_id: str, embedding: dict, rerank: dict) -> dict:
            return {
                "enabled": True,
                "disabled_reason": None,
                "embedding": embedding,
                "api_key": embedding.get("api_key"),
            }

        with patch("app.services.memory_retrieval_service.vector_rag_status", side_effect=_fake_vector_status):
            client = TestClient(self.app)
            resp = client.post(
                "/api/projects/p1/memory/preview",
                headers={"X-Test-User": "u_owner"},
                json={
                    "query_text": "hello",
                    "section_enabled": {
                        "worldbook": False,
                        "story_memory": False,
                        "structured": False,
                        "vector_rag": False,
                        "graph": False,
                        "fractal": False,
                    },
                },
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        keys = _collect_keys(payload)
        self.assertNotIn("api_key", keys)
        self.assertNotIn(secret, json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
