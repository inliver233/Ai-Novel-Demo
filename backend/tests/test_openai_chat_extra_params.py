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


if __name__ == "__main__":
    unittest.main()

