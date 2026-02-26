from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.structured_memory import (
    MemoryChangeSet,
    MemoryChangeSetItem,
    MemoryEntity,
    MemoryEvidence,
    MemoryEvent,
    MemoryRelation,
)
from app.models.user import User
from app.services.generation_service import RecordedLlmResult
from app.services.graph_auto_update_service import graph_auto_update_v1
from app.services.memory_update_service import apply_memory_change_set


def _compact_json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TestGraphAutoUpdateService(unittest.TestCase):
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
                Outline.__table__,
                Chapter.__table__,
                LLMPreset.__table__,
                GenerationRun.__table__,
                MemoryEntity.__table__,
                MemoryRelation.__table__,
                MemoryEvent.__table__,
                MemoryEvidence.__table__,
                MemoryChangeSet.__table__,
                MemoryChangeSetItem.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="P1", genre=None, logline=None))
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md=None, structure_json=None))
            db.add(
                Chapter(
                    id="c1",
                    project_id="p1",
                    outline_id="o1",
                    number=1,
                    title="Ch1",
                    plan=None,
                    content_md="Alice meets Bob.",
                    summary=None,
                    status="done",
                )
            )
            db.add(LLMPreset(project_id="p1", provider="openai", base_url=None, model="gpt-test"))
            db.add(MemoryEntity(id="e1", project_id="p1", entity_type="character", name="Alice", summary_md=None, attributes_json=None))
            db.commit()

    def test_graph_auto_update_v1_proposes_change_set(self) -> None:
        ev1 = "00000000-0000-0000-0000-0000000000e1"
        e2 = "00000000-0000-0000-0000-000000000002"
        model_out = _compact_json_dumps(
            {
                "title": "Graph Auto Update",
                "summary_md": "auto",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "evidence",
                        "target_id": ev1,
                        "after": {"source_type": "chapter", "source_id": "c1", "quote_md": "Alice meets Bob."},
                        "evidence_ids": [],
                    },
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": e2,
                        "after": {"entity_type": "character", "name": "Bob"},
                        "evidence_ids": [ev1],
                    },
                    {
                        "op": "upsert",
                        "target_table": "relations",
                        "target_id": None,
                        "after": {
                            "from_entity_id": "e1",
                            "to_entity_id": e2,
                            "relation_type": "friend",
                            "description_md": "Alice and Bob are friends.",
                            "attributes": {"strength": 0.7, "status": "active"},
                        },
                        "evidence_ids": [ev1],
                    },
                ],
            }
        )

        with patch("app.services.graph_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.graph_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.graph_auto_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=model_out,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-test",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test"}],
            ),
        ):
            res = graph_auto_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                change_set_idempotency_key="graphupd-12345678",
                focus=None,
            )

        self.assertTrue(bool(res.get("ok")))
        self.assertEqual(res.get("project_id"), "p1")
        self.assertEqual(res.get("chapter_id"), "c1")
        self.assertIn("change_set", res)
        self.assertEqual(len(res.get("items") or []), 3)

    def test_graph_auto_update_v1_repairs_parse_failed_once(self) -> None:
        invalid = _compact_json_dumps(
            {
                "title": "Graph Auto Update",
                "summary_md": "auto",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "entity_id": "00000000-0000-0000-0000-000000000002",
                        "after": {"entity_type": "character", "name": "Bob"},
                        "evidence_ids": [],
                    }
                ],
            }
        )
        repaired_value = {
            "title": "Graph Auto Update",
            "summary_md": "auto",
            "ops": [
                {
                    "op": "upsert",
                    "target_table": "entities",
                    "target_id": "00000000-0000-0000-0000-000000000002",
                    "after": {"entity_type": "character", "name": "Bob"},
                    "evidence_ids": [],
                }
            ],
        }

        with patch("app.services.graph_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.graph_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.graph_auto_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=invalid,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-orig",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-orig"}],
            ),
        ), patch(
            "app.services.graph_auto_update_service.repair_json_once",
            return_value={
                "ok": True,
                "repair_run_id": "run-repair",
                "value": repaired_value,
                "raw_json": _compact_json_dumps(repaired_value),
                "finish_reason": "stop",
                "warnings": [],
            },
        ):
            res = graph_auto_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                change_set_idempotency_key="graphupd-12345678",
                focus=None,
            )

        self.assertTrue(bool(res.get("ok")))
        self.assertEqual(res.get("run_id"), "run-orig")
        self.assertEqual(res.get("repair_run_id"), "run-repair")

    def test_graph_auto_update_v1_ops_empty_is_noop(self) -> None:
        model_out = _compact_json_dumps({"title": "Graph Auto Update", "summary_md": "auto", "ops": []})

        with patch("app.services.graph_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.graph_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.graph_auto_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=model_out,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-test-noop",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test-noop"}],
            ),
        ), patch("app.services.graph_auto_update_service.propose_chapter_memory_change_set") as mock_propose:
            res = graph_auto_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                change_set_idempotency_key="graphupd-12345678",
                focus=None,
            )

        self.assertTrue(bool(res.get("ok")))
        self.assertTrue(bool(res.get("no_op")))
        self.assertEqual(res.get("run_id"), "run-test-noop")
        self.assertIn("graph_auto_update_noop", res.get("warnings") or [])
        mock_propose.assert_not_called()

    def test_graph_auto_update_v1_rejects_evidence_source_id_mismatch(self) -> None:
        model_out = _compact_json_dumps(
            {
                "title": "Graph Auto Update",
                "summary_md": "auto",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "evidence",
                        "target_id": "00000000-0000-0000-0000-0000000000e1",
                        "after": {"source_type": "chapter", "source_id": "c2", "quote_md": "bad"},
                        "evidence_ids": [],
                    }
                ],
            }
        )

        with patch("app.services.graph_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.graph_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.graph_auto_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=model_out,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-test",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test"}],
            ),
        ):
            res = graph_auto_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                change_set_idempotency_key="graphupd-12345678",
                focus=None,
            )

        self.assertFalse(bool(res.get("ok")))
        self.assertEqual(res.get("reason"), "evidence_source_id_mismatch")
        self.assertEqual(res.get("source_id"), "c2")

    def test_graph_auto_update_v1_filters_attributes_keys(self) -> None:
        ev1 = "00000000-0000-0000-0000-0000000000e1"
        e2 = "00000000-0000-0000-0000-000000000002"
        model_out = _compact_json_dumps(
            {
                "title": "Graph Auto Update",
                "summary_md": "auto",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "evidence",
                        "target_id": ev1,
                        "after": {"source_type": "chapter", "source_id": "c1", "quote_md": "Alice meets Bob."},
                        "evidence_ids": [],
                    },
                    {
                        "op": "upsert",
                        "target_table": "entities",
                        "target_id": e2,
                        "after": {
                            "entity_type": "character",
                            "name": "Bob",
                            "attributes": {"aliases": ["B"], "unknown_key": "x"},
                        },
                        "evidence_ids": [ev1],
                    },
                    {
                        "op": "upsert",
                        "target_table": "relations",
                        "target_id": None,
                        "after": {
                            "from_entity_id": "e1",
                            "to_entity_id": e2,
                            "relation_type": "friend",
                            "description_md": "Alice and Bob are friends.",
                            "attributes": {"strength": 0.7, "status": "active", "unknown_key": "x"},
                        },
                        "evidence_ids": [ev1],
                    },
                ],
            }
        )

        with patch("app.services.graph_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.graph_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.graph_auto_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=model_out,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-test",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test"}],
            ),
        ):
            res = graph_auto_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                change_set_idempotency_key="graphupd-12345678",
                focus=None,
            )

        self.assertTrue(bool(res.get("ok")))
        warnings = list(res.get("warnings") or [])
        self.assertTrue(any("dropped_entity_attributes_keys" in str(w) for w in warnings))
        self.assertTrue(any("dropped_relation_attributes_keys" in str(w) for w in warnings))

        items = list(res.get("items") or [])
        entity_item = next(i for i in items if i.get("target_table") == "entities")
        entity_after = json.loads(str(entity_item.get("after_json") or "{}"))
        self.assertEqual(entity_after.get("name"), "Bob")
        entity_attrs = entity_after.get("attributes") or {}
        self.assertIn("aliases", entity_attrs)
        self.assertNotIn("unknown_key", entity_attrs)

        relation_item = next(i for i in items if i.get("target_table") == "relations")
        relation_after = json.loads(str(relation_item.get("after_json") or "{}"))
        relation_attrs = relation_after.get("attributes") or {}
        self.assertIn("strength", relation_attrs)
        self.assertIn("status", relation_attrs)
        self.assertNotIn("unknown_key", relation_attrs)

    def test_graph_auto_update_v1_allows_events_and_apply_inserts_event(self) -> None:
        ev1 = "00000000-0000-0000-0000-0000000000e1"
        event_id = "00000000-0000-0000-0000-0000000000f1"
        model_out = _compact_json_dumps(
            {
                "title": "Graph Auto Update",
                "summary_md": "auto",
                "ops": [
                    {
                        "op": "upsert",
                        "target_table": "evidence",
                        "target_id": ev1,
                        "after": {"source_type": "chapter", "source_id": "c1", "quote_md": "Alice meets Bob."},
                        "evidence_ids": [],
                    },
                    {
                        "op": "upsert",
                        "target_table": "events",
                        "target_id": event_id,
                        "after": {
                            "event_type": "encounter",
                            "title": "Alice meets Bob",
                            "content_md": "Alice meets Bob.",
                        },
                        "evidence_ids": [ev1],
                    },
                ],
            }
        )

        with patch("app.services.graph_auto_update_service.SessionLocal", self.SessionLocal), patch(
            "app.services.graph_auto_update_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.graph_auto_update_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=model_out,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-test",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test"}],
            ),
        ):
            res = graph_auto_update_v1(
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                change_set_idempotency_key="graphupd-12345678",
                focus=None,
            )

        self.assertTrue(bool(res.get("ok")))
        items = list(res.get("items") or [])
        self.assertTrue(any(i.get("target_table") == "events" for i in items))

        change_set_id = str((res.get("change_set") or {}).get("id") or "")
        self.assertTrue(change_set_id)

        with self.SessionLocal() as db:
            change_set = db.get(MemoryChangeSet, change_set_id)
            self.assertIsNotNone(change_set)
            apply_memory_change_set(db=db, request_id="rid-test", actor_user_id="u1", change_set=change_set)  # type: ignore[arg-type]
            row = db.get(MemoryEvent, event_id)

        self.assertIsNotNone(row)
        self.assertEqual(str(getattr(row, "chapter_id", "") or ""), "c1")
