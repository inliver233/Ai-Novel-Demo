import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


class TestGeminiThinkingConfigNonStream(unittest.TestCase):
    def test_drops_thinking_config_after_400_and_retries(self) -> None:
        seen_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(payload)
            generation_config = payload.get("generationConfig") or {}
            if len(seen_payloads) == 1:
                self.assertIn("thinkingConfig", generation_config)
                return httpx.Response(400, json={"error": {"message": "thinkingConfig unsupported"}})
            self.assertNotIn("thinkingConfig", generation_config)
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "pong"}]}, "finishReason": "STOP"}]},
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="gemini",
                    base_url="http://stubbed-gemini.local",
                    model="gemini-test",
                    api_key="sk-gem-test",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 128, "temperature": 0.2},
                    timeout_seconds=30,
                    extra={"thinkingConfig": {"thinkingBudget": 256, "includeThoughts": True}},
                )

        self.assertEqual(result.text, "pong")
        self.assertIn("thinkingConfig", result.dropped_params)
        self.assertGreaterEqual(len(seen_payloads), 2)


if __name__ == "__main__":
    unittest.main()
