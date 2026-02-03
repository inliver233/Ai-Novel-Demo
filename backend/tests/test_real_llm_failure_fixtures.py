from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from app.schemas.characters_auto_update import CharactersAutoUpdateV1Request
from app.schemas.worldbook_auto_update import WorldbookAutoUpdateV1Request
from app.services.output_contracts import contract_for_task
from app.services.output_parsers import extract_json_value


FIX_DIR = Path(__file__).parent / "fixtures" / "real_llm_failures"


class TestRealLlmFailureFixtures(unittest.TestCase):
    def test_fixtures_are_present(self) -> None:
        self.assertTrue(FIX_DIR.exists())
        index_path = FIX_DIR / "index.json"
        self.assertTrue(index_path.exists())

        items = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(items), 5)
        for item in items:
            self.assertTrue((FIX_DIR / item["file"]).exists(), msg=item)

    def test_fixtures_sanitized_no_api_keys(self) -> None:
        for path in FIX_DIR.glob("*"):
            if path.is_dir():
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotRegex(raw, r"sk-[A-Za-z0-9]{10,}", msg=str(path))
            lowered = raw.lower()
            self.assertNotIn("api_key", lowered, msg=str(path))
            self.assertNotIn("authorization:", lowered, msg=str(path))

    def test_characters_auto_update_fixture_reproduces_schema_drift(self) -> None:
        p = FIX_DIR / "b497cd7a-ed94-4171-8392-8e7f28773e48.characters_auto_update.output.txt"
        text = p.read_text(encoding="utf-8")
        value, _raw_json = extract_json_value(text)

        self.assertIsInstance(value, dict)
        self.assertEqual(value.get("schema_version"), "characters_auto_update_v1")
        self.assertIsInstance(value.get("ops"), list)
        self.assertIn("character", value["ops"][0])

        parsed = CharactersAutoUpdateV1Request.model_validate(value)
        self.assertEqual(parsed.ops[0].op, "upsert")
        self.assertEqual(parsed.ops[0].name, "光头强")
        self.assertIsInstance(parsed.ops[0].patch, dict)

    def test_worldbook_auto_update_fixture_reproduces_schema_drift(self) -> None:
        p = FIX_DIR / "d8024a18-3416-47df-8656-9da9c669853f.worldbook_auto_update.output.txt"
        text = p.read_text(encoding="utf-8")
        value, _raw_json = extract_json_value(text)

        self.assertIsInstance(value, dict)
        self.assertEqual(value.get("schema_version"), "worldbook_auto_update_v1")
        self.assertIsInstance(value.get("ops"), list)
        self.assertIn("item", value["ops"][0])

        parsed = WorldbookAutoUpdateV1Request.model_validate(value)
        self.assertEqual(parsed.ops[0].op, "create")
        entry0 = parsed.ops[0].entry or {}
        self.assertIn("content_md", entry0)
        self.assertNotIn("content", entry0)
        self.assertIn(str(entry0.get("priority") or ""), {"drop_first", "optional", "important", "must"})

    def test_graph_auto_update_fixture_missing_memory_update_envelope(self) -> None:
        p = FIX_DIR / "ea1ca685-7989-49cb-8767-f3d883a7ea05.graph_auto_update.output.txt"
        text = p.read_text(encoding="utf-8")
        value, _raw_json = extract_json_value(text)

        self.assertIsInstance(value, dict)
        self.assertNotIn("schema_version", value)
        self.assertNotIn("idempotency_key", value)
        self.assertIsInstance(value.get("ops"), list)

        contract = contract_for_task("memory_update")
        parsed = contract.parse(text)
        self.assertIsNone(parsed.parse_error, msg=str(parsed.parse_error))

        ops = list((parsed.data or {}).get("ops") or [])
        self.assertGreaterEqual(len(ops), 1)
        self.assertEqual(ops[0].get("target_table"), "entities")
        self.assertEqual(ops[0].get("target_id"), "ca4e3e50-6cb7-4983-af1a-94775a7b676d")
        after0 = ops[0].get("after") or {}
        self.assertEqual(after0.get("entity_type"), "person")

    def test_table_ai_update_timeout_fixtures(self) -> None:
        ids = [
            "938e0135-960c-4c7a-9337-126fc2026d38",
            "7d9b53d8-f7df-4ccd-900f-a53c6b5151a5",
        ]
        for run_id in ids:
            p = FIX_DIR / f"{run_id}.table_ai_update.error.json"
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data.get("code"), "LLM_TIMEOUT")
            details = data.get("details") or {}
            self.assertEqual(details.get("status_code"), 504)
            upstream_error = str(details.get("upstream_error") or "")
            upstream_error = re.sub(r"\\s+", " ", upstream_error).strip().lower()
            self.assertTrue(
                upstream_error.startswith("<!doctype html") or upstream_error.startswith("<html"),
                msg=run_id,
            )
