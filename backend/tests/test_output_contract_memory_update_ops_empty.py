from __future__ import annotations

import unittest

from app.services.output_contracts import OutputContract


class TestOutputContractMemoryUpdateOpsEmpty(unittest.TestCase):
    def test_ops_empty_is_allowed_as_noop(self) -> None:
        contract = OutputContract(type="memory_update_json")
        parsed = contract.parse('{"title":"t","summary_md":"s","ops":[]}')
        self.assertIsNone(parsed.parse_error)
        self.assertIn("ops_empty", parsed.warnings)
        self.assertEqual(len(parsed.data.get("ops") or []), 0)

    def test_ops_missing_is_allowed_as_noop(self) -> None:
        contract = OutputContract(type="memory_update_json")
        parsed = contract.parse('{"title":"t"}')
        self.assertIsNone(parsed.parse_error)
        self.assertIn("ops_missing", parsed.warnings)
        self.assertEqual(len(parsed.data.get("ops") or []), 0)


if __name__ == "__main__":
    unittest.main()

