from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.graph_context_service import query_graph_context


class TestGraphContextErrorSanitization(unittest.TestCase):
    def test_query_graph_context_does_not_echo_exception_message(self) -> None:
        secret = "sk-test-SECRET1234"

        with patch(
            "app.services.graph_context_service._load_match_candidates",
            side_effect=ValueError(f"boom {secret}"),
        ):
            out = query_graph_context(db=None, project_id="p1", query_text="dragon")

        self.assertIn("error", out)
        self.assertNotIn(secret, str(out.get("error") or ""))


if __name__ == "__main__":
    unittest.main()

