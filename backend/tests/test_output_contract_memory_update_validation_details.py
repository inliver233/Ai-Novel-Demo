import unittest

from app.services.output_contracts import OutputContract


class TestOutputContractMemoryUpdateValidationDetails(unittest.TestCase):
    def test_memory_update_json_schema_invalid_includes_idx_and_pydantic_errors(self) -> None:
        contract = OutputContract(type="memory_update_json")
        text = '{"ops":[{"op":"upsert","target_table":"entities","after":{"name":""}}]}'
        res = contract.parse(text)
        self.assertIsNotNone(res.parse_error)
        assert res.parse_error is not None
        self.assertEqual(res.parse_error.get("code"), "MEMORY_UPDATE_PARSE_ERROR")
        self.assertEqual(res.parse_error.get("idx"), 0)
        errors = res.parse_error.get("errors")
        self.assertIsInstance(errors, list)
        self.assertGreaterEqual(len(errors or []), 1)
        for e in errors or []:
            self.assertNotIn("input", e)


if __name__ == "__main__":
    unittest.main()

