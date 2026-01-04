import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm, call_llm_messages
from app.llm.messages import ChatMessage


class TestGeminiApiKeyHeader(unittest.TestCase):
    def test_call_llm_sends_key_in_header_not_query(self) -> None:
        api_key = "gemini-test-SECRET1234"

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.query, b"")
            self.assertNotIn("key", request.url.params)
            self.assertEqual(request.headers.get("x-goog-api-key"), api_key)
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "pong"}]},
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm(
                    provider="gemini",
                    base_url="http://stubbed-gemini.local",
                    model="gemini-test",
                    api_key=api_key,
                    system="",
                    user="hi",
                    params={},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")

    def test_call_llm_messages_sends_key_in_header_not_query(self) -> None:
        api_key = "gemini-test-SECRET5678"

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.query, b"")
            self.assertNotIn("key", request.url.params)
            self.assertEqual(request.headers.get("x-goog-api-key"), api_key)
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "pong"}]},
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="gemini",
                    base_url="http://stubbed-gemini.local",
                    model="gemini-test",
                    api_key=api_key,
                    messages=[ChatMessage(role="user", content="hi")],
                    params={},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")


if __name__ == "__main__":
    unittest.main()

