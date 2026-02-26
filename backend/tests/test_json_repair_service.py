import unittest
from unittest.mock import patch

from app.services.generation_service import PreparedLlmCall, RecordedLlmResult
from app.services.json_repair_service import repair_json_once
from app.services.llm_retry import LlmRetryExhausted


class TestJsonRepairService(unittest.TestCase):
    def test_repair_success_returns_value_and_repair_run_id(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={},
            params_json="{}",
            extra={},
        )
        recorded = RecordedLlmResult(
            text='{"ok":true,"ops":[]}',
            finish_reason="stop",
            latency_ms=1,
            dropped_params=[],
            run_id="run-repair",
        )

        with patch(
            "app.services.json_repair_service.call_llm_and_record_with_retries",
            return_value=(recorded, [{"attempt": 1, "request_id": "rid", "run_id": "run-repair"}]),
        ):
            res = repair_json_once(
                request_id="rid",
                actor_user_id="u1",
                project_id="p1",
                chapter_id=None,
                api_key="sk-test-SECRET1234",
                llm_call=llm_call,
                raw_output="not json",
                schema='{"ops":[...]}',
                expected_root="object",
                origin_run_id="run-orig",
                origin_task="memory_update",
            )

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("repair_run_id"), "run-repair")
        self.assertIsInstance(res.get("value"), dict)

    def test_repair_parse_failed_returns_parse_error(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={},
            params_json="{}",
            extra={},
        )
        recorded = RecordedLlmResult(
            text="not json",
            finish_reason="stop",
            latency_ms=1,
            dropped_params=[],
            run_id="run-repair",
        )

        with patch(
            "app.services.json_repair_service.call_llm_and_record_with_retries",
            return_value=(recorded, [{"attempt": 1, "request_id": "rid", "run_id": "run-repair"}]),
        ):
            res = repair_json_once(
                request_id="rid",
                actor_user_id="u1",
                project_id="p1",
                chapter_id=None,
                api_key="sk-test-SECRET1234",
                llm_call=llm_call,
                raw_output="not json",
                schema="{}",
                expected_root="object",
            )

        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("reason"), "parse_failed")
        self.assertEqual(res.get("repair_run_id"), "run-repair")
        self.assertIsInstance((res.get("parse_error") or {}).get("message"), str)

    def test_repair_llm_call_failed_returns_repair_run_id_from_exception(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={},
            params_json="{}",
            extra={},
        )

        last_exc = TimeoutError("boom")

        with patch(
            "app.services.json_repair_service.call_llm_and_record_with_retries",
            side_effect=LlmRetryExhausted(
                error_type="TimeoutError",
                error_message="boom",
                error_code="LLM_TIMEOUT",
                status_code=408,
                run_id="run-failed",
                attempts=[{"attempt": 1, "request_id": "rid", "run_id": "run-failed", "error_code": "LLM_TIMEOUT"}],
                last_exception=last_exc,
            ),
        ):
            res = repair_json_once(
                request_id="rid",
                actor_user_id="u1",
                project_id="p1",
                chapter_id=None,
                api_key="sk-test-SECRET1234",
                llm_call=llm_call,
                raw_output="not json",
                schema="{}",
                expected_root="object",
            )

        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("reason"), "llm_call_failed")
        self.assertEqual(res.get("repair_run_id"), "run-failed")


if __name__ == "__main__":
    unittest.main()
