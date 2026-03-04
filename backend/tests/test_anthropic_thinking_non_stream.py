import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


class TestAnthropicThinkingNonStream(unittest.TestCase):
    def test_includes_thinking_and_beta_header(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            self.assertEqual(payload.get("thinking"), {"type": "enabled", "budget_tokens": 256})
            self.assertEqual(request.headers.get("anthropic-beta"), "thinking-2025-05-14")
            return httpx.Response(200, json={"content": [{"type": "text", "text": "pong"}], "stop_reason": "end_turn"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="anthropic",
                    base_url="http://stubbed-anthropic.local",
                    model="claude-test",
                    api_key="sk-ant-test",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 256},
                    timeout_seconds=30,
                    extra={"thinking": {"type": "enabled", "budget_tokens": 256}, "anthropic_beta": "thinking-2025-05-14"},
                )

        self.assertEqual(result.text, "pong")
        self.assertEqual(result.finish_reason, "end_turn")


if __name__ == "__main__":
    unittest.main()
