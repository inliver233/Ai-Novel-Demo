import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


class TestOpenAiDowngradeRetry(unittest.TestCase):
    def test_drops_params_until_upstream_accepts(self) -> None:
        seen_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/chat/completions"))

            payload = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(payload)

            # Simulate a picky gateway/model that rejects otherwise-valid parameters.
            if "stop" in payload:
                return httpx.Response(400, json={"error": {"message": "stop unsupported"}})
            if "top_p" in payload:
                return httpx.Response(400, json={"error": {"message": "top_p unsupported"}})
            if "temperature" in payload:
                return httpx.Response(400, json={"error": {"message": "temperature unsupported"}})

            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]},
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai",
                    base_url="http://stubbed-openai.local",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"stop": ["x"], "top_p": 0.9, "temperature": 0.1},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text.strip(), "pong")
        self.assertGreaterEqual(len(seen_payloads), 4)
        self.assertIn("stop", seen_payloads[0])
        self.assertNotIn("stop", seen_payloads[1])
        self.assertNotIn("top_p", seen_payloads[2])
        self.assertNotIn("temperature", seen_payloads[-1])
        self.assertIn("stop", result.dropped_params)
        self.assertIn("top_p", result.dropped_params)
        self.assertIn("temperature", result.dropped_params)


if __name__ == "__main__":
    unittest.main()

