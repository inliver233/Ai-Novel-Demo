from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import AppError
from app.schemas.llm_test import LLMTestRequest
from app.services.llm_test_app_service import llm_test, prepare_llm_test_request


class TestLlmTestAppService(unittest.TestCase):
    def test_prepare_llm_test_request_applies_provider_defaults(self) -> None:
        prepared = prepare_llm_test_request(
            user_id="user-1",
            body=LLMTestRequest(provider="openai", model="gpt-test", timeout_seconds=5),
            x_llm_provider=None,
            x_llm_api_key="sk-test",
        )

        self.assertEqual(prepared.base_url, "https://api.openai.com/v1")
        self.assertEqual(prepared.context["base_url_host"], "api.openai.com")
        self.assertEqual(prepared.params["max_tokens"], 64)
        self.assertEqual(prepared.params["temperature"], 0)
        self.assertEqual(prepared.resolved_api_key, "sk-test")

    @patch("app.services.llm_test_app_service.call_llm")
    @patch("app.services.llm_test_app_service.time.sleep")
    @patch("app.services.llm_test_app_service.compute_backoff_seconds", return_value=0)
    @patch("app.services.llm_test_app_service.task_llm_max_attempts", return_value=2)
    def test_llm_test_retryable_error_includes_attempt_details(
        self,
        _max_attempts,
        _compute_backoff,
        mock_sleep,
        mock_call,
    ) -> None:
        timeout_exc = AppError(code="LLM_TIMEOUT", message="timeout", status_code=504, details={"status_code": 504})
        mock_call.side_effect = [timeout_exc, timeout_exc]

        with self.assertRaises(AppError) as ctx:
            llm_test(
                user_id="user-1",
                body=LLMTestRequest(provider="openai", model="gpt-test", timeout_seconds=5),
                x_llm_provider=None,
                x_llm_api_key="sk-test",
            )

        self.assertEqual(ctx.exception.code, "LLM_TIMEOUT")
        self.assertEqual(ctx.exception.details["attempt_max"], 2)
        self.assertEqual(len(ctx.exception.details["attempts"]), 2)
        self.assertEqual(ctx.exception.details["provider"], "openai")
        self.assertEqual(ctx.exception.details["base_url_host"], "api.openai.com")
        mock_sleep.assert_not_called()

    @patch("app.services.llm_test_app_service.call_llm")
    @patch("app.services.llm_test_app_service.compute_backoff_seconds", return_value=0)
    @patch("app.services.llm_test_app_service.task_llm_max_attempts", return_value=2)
    def test_llm_test_returns_trimmed_preview(self, _max_attempts, _compute_backoff, mock_call) -> None:
        mock_call.return_value = SimpleNamespace(
            text="x" * 260,
            latency_ms=12,
            finish_reason="stop",
            dropped_params=["temperature"],
        )

        out = llm_test(
            user_id="user-1",
            body=LLMTestRequest(provider="openai", model="gpt-test", timeout_seconds=5),
            x_llm_provider=None,
            x_llm_api_key="sk-test",
        )

        self.assertEqual(len(out["text"]), 200)
        self.assertEqual(out["latency_ms"], 12)
        self.assertEqual(out["finish_reason"], "stop")
        self.assertEqual(out["dropped_params"], ["temperature"])


if __name__ == "__main__":
    unittest.main()
