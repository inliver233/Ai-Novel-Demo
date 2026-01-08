import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


class TestOpenAiChatExtraParams(unittest.TestCase):
    def test_max_completion_tokens_in_extra_removes_max_tokens(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            self.assertIn("max_completion_tokens", payload)
            self.assertEqual(payload["max_completion_tokens"], 50)
            self.assertNotIn("max_tokens", payload)
            return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai",
                    base_url="http://stubbed-openai.local",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 999},
                    timeout_seconds=30,
                    extra={"max_completion_tokens": 50},
                )

        self.assertEqual(result.text, "pong")

    def test_response_format_is_dropped_after_400_and_recorded(self) -> None:
        seen_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(payload)
            if "response_format" in payload:
                return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai",
                    base_url="http://stubbed-openai.local",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"temperature": 0.1},
                    timeout_seconds=30,
                    extra={"response_format": {"type": "json_object"}},
                )

        self.assertEqual(result.text, "pong")
        self.assertGreaterEqual(len(seen_payloads), 2)
        self.assertIn("response_format", seen_payloads[0])
        self.assertNotIn("response_format", seen_payloads[-1])
        self.assertIn("response_format", result.dropped_params)

    def test_appends_v1_on_404_and_retries(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/openai/chat/completions"):
                return httpx.Response(404, json={"error": {"message": "not found"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_compatible",
                    base_url="http://stubbed-openai.local/openai",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")
        self.assertGreaterEqual(len(seen_paths), 2)
        self.assertEqual(seen_paths[0], "/openai/chat/completions")
        self.assertEqual(seen_paths[-1], "/openai/v1/chat/completions")

    def test_falls_back_to_responses_when_gateway_rejects_messages(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/chat/completions"):
                return httpx.Response(400, json={"detail": "Unsupported parameter: messages"})
            if request.url.path.endswith("/responses"):
                return httpx.Response(200, json={"output_text": "pong", "status": "completed"})
            return httpx.Response(404, json={"error": {"message": "not found"}})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_compatible",
                    base_url="http://stubbed-openai.local/openai",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12, "temperature": 0},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")
        self.assertTrue(any(path.endswith("/chat/completions") for path in seen_paths))
        self.assertTrue(any(path.endswith("/responses") for path in seen_paths))


if __name__ == "__main__":
    unittest.main()
