import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import AppError
from app.services.generation_service import PreparedLlmCall, call_llm_and_record


class TestGenerationServiceRecordsErrors(unittest.TestCase):
    def test_non_app_error_is_recorded(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={},
            params_json="{}",
            extra={},
        )

        api_key = "sk-test-SECRET1234"
        with patch("app.services.generation_service.call_llm", side_effect=ValueError("boom")):
            with patch("app.services.generation_service.write_generation_run", return_value="run_1") as write_mock:
                with self.assertRaises(ValueError) as cm:
                    call_llm_and_record(
                        logger=logging.getLogger("test"),
                        request_id="rid",
                        actor_user_id="u",
                        project_id="p",
                        chapter_id=None,
                        run_type="test",
                        api_key=api_key,
                        prompt_system="sys",
                        prompt_user="user",
                        llm_call=llm_call,
                    )

                self.assertEqual(getattr(cm.exception, "run_id", None), "run_1")
                self.assertTrue(write_mock.called)
                kwargs = write_mock.call_args.kwargs
                self.assertIn("error_json", kwargs)
                self.assertIsNotNone(kwargs["error_json"])
                self.assertIn("INTERNAL_ERROR", kwargs["error_json"])
                self.assertNotIn(api_key, kwargs["error_json"])
                params = json.loads(kwargs["params_json"])
                self.assertIn("memory_retrieval_log_json", params)
                self.assertIsInstance(params["memory_retrieval_log_json"], dict)

    def test_app_error_is_raised_with_run_id_in_details(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={},
            params_json="{}",
            extra={},
        )

        with patch(
            "app.services.generation_service.call_llm",
            side_effect=AppError(code="LLM_KEY_MISSING", message="missing", status_code=401, details={}),
        ):
            with patch("app.services.generation_service.write_generation_run", return_value="run_2"):
                with self.assertRaises(AppError) as cm:
                    call_llm_and_record(
                        logger=logging.getLogger("test"),
                        request_id="rid",
                        actor_user_id="u",
                        project_id="p",
                        chapter_id=None,
                        run_type="test",
                        api_key="sk-test-SECRET1234",
                        prompt_system="sys",
                        prompt_user="user",
                        llm_call=llm_call,
                    )

        self.assertEqual(cm.exception.details.get("run_id"), "run_2")

    def test_success_records_memory_retrieval_log_placeholder(self) -> None:
        llm_call = PreparedLlmCall(
            provider="openai",
            model="gpt-test",
            base_url="https://example.invalid",
            timeout_seconds=30,
            params={"temperature": 0.7},
            params_json=json.dumps({"temperature": 0.7}, ensure_ascii=False),
            extra={},
        )

        with patch(
            "app.services.generation_service.call_llm",
            return_value=SimpleNamespace(text="ok", finish_reason="stop", latency_ms=1, dropped_params=[]),
        ):
            with patch("app.services.generation_service.write_generation_run", return_value="run_1") as write_mock:
                call_llm_and_record(
                    logger=logging.getLogger("test"),
                    request_id="rid",
                    actor_user_id="u",
                    project_id="p",
                    chapter_id=None,
                    run_type="test",
                    api_key="sk-test-SECRET1234",
                    prompt_system="sys",
                    prompt_user="user",
                    llm_call=llm_call,
                )

                kwargs = write_mock.call_args.kwargs
                params = json.loads(kwargs["params_json"])
                self.assertIn("memory_retrieval_log_json", params)
                self.assertIsInstance(params["memory_retrieval_log_json"], dict)


if __name__ == "__main__":
    unittest.main()
