import logging
import unittest
from unittest.mock import patch

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
                with self.assertRaises(ValueError):
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

                self.assertTrue(write_mock.called)
                kwargs = write_mock.call_args.kwargs
                self.assertIn("error_json", kwargs)
                self.assertIsNotNone(kwargs["error_json"])
                self.assertIn("INTERNAL_ERROR", kwargs["error_json"])
                self.assertNotIn(api_key, kwargs["error_json"])


if __name__ == "__main__":
    unittest.main()
