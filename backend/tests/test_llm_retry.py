from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from app.core.errors import AppError
from app.services.generation_service import PreparedLlmCall, RecordedLlmResult
from app.services.llm_retry import (
    LlmRetryExhausted,
    build_retry_request_id,
    call_llm_and_record_with_retries,
    is_retryable_llm_error,
    run_id_from_exc,
)


class TestLlmRetryHelpers(unittest.TestCase):
    def test_build_retry_request_id_clamps_to_64_chars(self) -> None:
        base = "x" * 80
        rid1 = build_retry_request_id(base, attempt=1)
        self.assertEqual(len(rid1), 64)
        rid2 = build_retry_request_id(base, attempt=2)
        self.assertTrue(rid2.endswith(":retry1"))
        self.assertLessEqual(len(rid2), 64)

    def test_run_id_from_app_error_details(self) -> None:
        exc = AppError(code="LLM_TIMEOUT", message="timeout", status_code=504, details={"run_id": "run-1"})
        self.assertEqual(run_id_from_exc(exc), "run-1")

    def test_run_id_from_exc_attribute(self) -> None:
        exc = ValueError("boom")
        setattr(exc, "run_id", "run-2")
        self.assertEqual(run_id_from_exc(exc), "run-2")

    def test_is_retryable_llm_error(self) -> None:
        self.assertTrue(is_retryable_llm_error(AppError(code="LLM_TIMEOUT", message="t", status_code=504)))
        self.assertTrue(is_retryable_llm_error(AppError(code="LLM_RATE_LIMIT", message="rl", status_code=429)))
        self.assertFalse(is_retryable_llm_error(AppError(code="LLM_BAD_REQUEST", message="bad", status_code=400)))

    def test_call_llm_and_record_with_retries_succeeds_after_timeout(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={"temperature": 0.2, "max_tokens": 1024},
            params_json="{}",
            extra={},
        )

        timeout_exc = AppError(code="LLM_TIMEOUT", message="timeout", status_code=504, details={"run_id": "run-orig"})
        ok = RecordedLlmResult(text="{}", finish_reason="stop", latency_ms=1, dropped_params=[], run_id="run-ok")
        sleeps: list[float] = []

        with patch("app.services.llm_retry.call_llm_and_record", side_effect=[timeout_exc, ok]) as mock_call:
            recorded, attempts = call_llm_and_record_with_retries(
                logger=logging.getLogger("test"),
                request_id="rid-0123456789",
                actor_user_id="u1",
                project_id="p1",
                chapter_id=None,
                run_type="t",
                api_key="masked_api_key",
                prompt_system="sys",
                prompt_user="user",
                llm_call=llm_call,
                max_attempts=3,
                sleep=lambda s: sleeps.append(float(s)),
                llm_call_overrides_by_attempt={1: {"max_tokens": 1024}, 2: {"max_tokens": 512}},
                backoff_base_seconds=0.01,
                backoff_max_seconds=0.02,
                jitter=0.0,
            )

        self.assertEqual(recorded.run_id, "run-ok")
        self.assertEqual(mock_call.call_count, 2)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].get("run_id"), "run-orig")
        self.assertTrue(str(attempts[1].get("request_id") or "").endswith(":retry1"))
        self.assertTrue(len(sleeps) >= 1)

    def test_call_llm_and_record_with_retries_does_not_retry_non_retryable(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={},
            params_json="{}",
            extra={},
        )

        bad = AppError(code="LLM_BAD_REQUEST", message="bad", status_code=400, details={"run_id": "run-1"})
        with patch("app.services.llm_retry.call_llm_and_record", side_effect=[bad]) as mock_call:
            with self.assertRaises(LlmRetryExhausted) as cm:
                call_llm_and_record_with_retries(
                    logger=logging.getLogger("test"),
                    request_id="rid",
                    actor_user_id="u1",
                    project_id="p1",
                    chapter_id=None,
                    run_type="t",
                    api_key="masked_api_key",
                    prompt_system="sys",
                    prompt_user="user",
                    llm_call=llm_call,
                    max_attempts=3,
                    sleep=lambda _: None,
                    jitter=0.0,
                )

        self.assertEqual(mock_call.call_count, 1)
        err = cm.exception
        self.assertEqual(err.error_code, "LLM_BAD_REQUEST")
        self.assertEqual(err.run_id, "run-1")
        self.assertEqual(len(list(err.attempts or [])), 1)


if __name__ == "__main__":
    unittest.main()

