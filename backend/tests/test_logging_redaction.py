from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import settings
from app.core.logging import exception_log_fields


class TestLoggingRedaction(unittest.TestCase):
    def test_exception_log_fields_redacts_common_secret_patterns(self) -> None:
        msg = (
            "boom "
            "https://example.com?key=AIzaSyDUMMY1234567890&api_key=sk-test-SECRET1234 "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
            "x-llm-api-key: sk-test-SECRET1234 "
            "raw_google=AIzaSyDUMMY1234567890"
        )
        exc = ValueError(msg)

        with patch.object(settings, "app_env", "dev"):
            fields = exception_log_fields(exc)

        redacted = str(fields.get("exception") or "")
        self.assertIn("key=****", redacted)
        self.assertIn("api_key=****", redacted)
        self.assertIn("Bearer ***", redacted)
        self.assertIn("x-llm-api-key: ***", redacted)
        self.assertIn("raw_google=AIza***", redacted)

        self.assertNotIn("sk-test-SECRET1234", redacted)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", redacted)
        self.assertNotIn("AIzaSyDUMMY1234567890", redacted)


if __name__ == "__main__":
    unittest.main()

