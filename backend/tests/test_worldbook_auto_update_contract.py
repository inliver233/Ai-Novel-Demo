from __future__ import annotations

import unittest

from app.services.output_contracts import contract_for_task


class TestWorldbookAutoUpdateContract(unittest.TestCase):
    def test_parses_valid_ops(self) -> None:
        contract = contract_for_task("worldbook_auto_update")
        raw = """
```json
{
  "schema_version": "worldbook_auto_update_v1",
  "title": "WB Auto Update",
  "summary_md": "ok",
  "ops": [
    {
      "op": "create",
      "entry": {
        "title": "龙族",
        "content_md": "设定：龙族……",
        "keywords": ["龙", "dragon"],
        "aliases": ["巨龙"],
        "enabled": true,
        "constant": false,
        "exclude_recursion": false,
        "prevent_recursion": false,
        "char_limit": 12000,
        "priority": "important"
      }
    },
    {
      "op": "dedupe",
      "canonical_title": "龙族",
      "duplicate_titles": ["龙类", "龙族（旧）"],
      "reason": "重复条目"
    }
  ]
}
```
"""
        parsed = contract.parse(raw)
        self.assertIsNone(parsed.parse_error)
        ops = parsed.data.get("ops") or []
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0].get("op"), "create")
        self.assertEqual((ops[0].get("entry") or {}).get("title"), "龙族")
        self.assertEqual(ops[1].get("op"), "dedupe")

    def test_parse_error_when_invalid_json(self) -> None:
        contract = contract_for_task("worldbook_auto_update")
        parsed = contract.parse("not a json")
        self.assertIsNotNone(parsed.parse_error)
        assert parsed.parse_error is not None
        self.assertEqual(parsed.parse_error.get("code"), "WORLDBOOK_AUTO_UPDATE_PARSE_ERROR")

    def test_schema_version_missing_is_allowed_as_v1(self) -> None:
        contract = contract_for_task("worldbook_auto_update")
        parsed = contract.parse('{"ops":[{"op":"dedupe","canonical_title":"A","duplicate_titles":["B"]}]}')
        self.assertIsNone(parsed.parse_error)
        self.assertIn("schema_version_missing", parsed.warnings)
        self.assertEqual(len(parsed.data.get("ops") or []), 1)

    def test_parse_error_when_ops_empty(self) -> None:
        contract = contract_for_task("worldbook_auto_update")
        parsed = contract.parse('{"schema_version":"worldbook_auto_update_v1","ops":[]}')
        self.assertIsNone(parsed.parse_error)
        self.assertIn("ops_empty", parsed.warnings)
        self.assertEqual(len(parsed.data.get("ops") or []), 0)

    def test_ops_missing_is_allowed_as_noop(self) -> None:
        contract = contract_for_task("worldbook_auto_update")
        parsed = contract.parse('{"schema_version":"worldbook_auto_update_v1","title":"t"}')
        self.assertIsNone(parsed.parse_error)
        self.assertIn("ops_missing", parsed.warnings)
        self.assertEqual(len(parsed.data.get("ops") or []), 0)

    def test_finish_reason_length_adds_warning(self) -> None:
        contract = contract_for_task("worldbook_auto_update")
        parsed = contract.parse(
            '{"schema_version":"worldbook_auto_update_v1","ops":[{"op":"dedupe","canonical_title":"A","duplicate_titles":["B"]}]}',
            finish_reason="length",
        )
        self.assertIsNone(parsed.parse_error)
        self.assertIn("output_truncated", parsed.warnings)
