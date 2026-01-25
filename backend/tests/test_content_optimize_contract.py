from __future__ import annotations

import unittest

from app.services.output_contracts import contract_for_task


class TestContentOptimizeContract(unittest.TestCase):
    def test_parses_content_tag_block(self) -> None:
        contract = contract_for_task("content_optimize")
        parsed = contract.parse("<content>hello</content>")
        self.assertEqual(parsed.parse_error, None)
        self.assertEqual(parsed.data.get("content_md"), "hello")

    def test_allows_content_tag_with_attributes(self) -> None:
        contract = contract_for_task("content_optimize")
        parsed = contract.parse('<content data-x="1">hello</content>')
        self.assertEqual(parsed.parse_error, None)
        self.assertEqual(parsed.data.get("content_md"), "hello")


if __name__ == "__main__":
    unittest.main()

