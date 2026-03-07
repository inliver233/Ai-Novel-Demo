from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from app.core.errors import AppError
from app.llm.client import call_llm


class TestLlmClientLogging(unittest.TestCase):
    def test_call_llm_enriches_provider_app_errors(self) -> None:
        upstream_error = AppError(
            code="LLM_UPSTREAM_ERROR",
            message="boom",
            status_code=502,
            details={"status_code": 503, "upstream_error": "gateway timeout"},
        )

        with patch("app.llm.providers.openai_chat.call_openai_chat_completions", side_effect=upstream_error):
            with self.assertRaises(AppError) as cm:
                call_llm(
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-test",
                    api_key="sk-test",
                    system="system",
                    user="user",
                    params={},
                    timeout_seconds=5,
                )

        details = cm.exception.details
        self.assertEqual(details.get("provider"), "openai")
        self.assertEqual(details.get("model"), "gpt-test")
        self.assertEqual(details.get("base_url_host"), "api.openai.com")
        self.assertEqual(details.get("timeout_seconds"), 5)
        self.assertEqual(details.get("status_code"), 503)
        self.assertEqual(details.get("upstream_error"), "gateway timeout")

    def test_call_llm_timeout_enriches_timeout_errors(self) -> None:
        with patch("app.llm.providers.openai_chat.call_openai_chat_completions", side_effect=httpx.ReadTimeout("timeout")):
            with self.assertRaises(AppError) as cm:
                call_llm(
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-test",
                    api_key="sk-test",
                    system="system",
                    user="user",
                    params={},
                    timeout_seconds=7,
                )

        exc = cm.exception
        self.assertEqual(exc.code, "LLM_TIMEOUT")
        self.assertEqual(exc.status_code, 504)
        self.assertEqual(exc.details.get("provider"), "openai")
        self.assertEqual(exc.details.get("model"), "gpt-test")
        self.assertEqual(exc.details.get("base_url_host"), "api.openai.com")
        self.assertEqual(exc.details.get("timeout_seconds"), 7)


if __name__ == "__main__":
    unittest.main()

