import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


class TestAnthropicMaxTokensRetry(unittest.TestCase):
    def test_max_tokens_is_clamped_from_error_message(self) -> None:
        seen_max_tokens: list[int | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/v1/messages"))

            payload = json.loads(request.content.decode("utf-8"))
            max_tokens = payload.get("max_tokens")
            seen_max_tokens.append(max_tokens if isinstance(max_tokens, int) else None)

            if isinstance(max_tokens, int) and max_tokens > 196608:
                error_body = {
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "invalid params, model[MiniMax-M2.1] does not support max tokens > 196608 (2013)",
                    },
                    "request_id": "stubbed_request_id",
                }
                raw = json.dumps(error_body, ensure_ascii=True).replace(">", "\\u003e")
                return httpx.Response(
                    400,
                    content=raw.encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )

            ok_body = {
                "content": [{"type": "text", "text": "pong"}],
                "stop_reason": "end_turn",
            }
            return httpx.Response(200, json=ok_body)

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="anthropic",
                    base_url="http://stubbed-anthropic.local",
                    model="MiniMax-M2.1",
                    api_key="dummy_api_key",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 200000, "temperature": 0},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text.strip(), "pong")
        self.assertGreaterEqual(len(seen_max_tokens), 2)
        self.assertEqual(seen_max_tokens[0], 200000)
        self.assertEqual(seen_max_tokens[1], 196608)


if __name__ == "__main__":
    unittest.main()

