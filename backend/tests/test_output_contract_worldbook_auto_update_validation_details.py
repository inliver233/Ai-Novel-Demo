import unittest

from app.services.output_contracts import OutputContract


class TestOutputContractWorldbookAutoUpdateValidationDetails(unittest.TestCase):
    def test_worldbook_auto_update_json_schema_invalid_includes_idx_and_pydantic_errors(self) -> None:
        contract = OutputContract(type="worldbook_auto_update_json")
        text = '{"schema_version":"worldbook_auto_update_v1","ops":[{"op":"update","match_title":"","entry":{"title":"X"}}]}'
        res = contract.parse(text)
        self.assertIsNotNone(res.parse_error)
        assert res.parse_error is not None
        self.assertEqual(res.parse_error.get("code"), "WORLDBOOK_AUTO_UPDATE_PARSE_ERROR")
        self.assertEqual(res.parse_error.get("idx"), 0)
        errors = res.parse_error.get("errors")
        self.assertIsInstance(errors, list)
        self.assertGreaterEqual(len(errors or []), 1)
        for e in errors or []:
            self.assertNotIn("input", e)


if __name__ == "__main__":
    unittest.main()

