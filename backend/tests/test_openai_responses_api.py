import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


class TestOpenAiResponsesApi(unittest.TestCase):
    def test_builds_text_format_from_response_format_and_parses_output_text(self) -> None:
        seen_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/responses"))
            payload = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(payload)

            self.assertEqual(payload.get("model"), "gpt-test")
            self.assertEqual(payload.get("max_output_tokens"), 12)

            text_cfg = payload.get("text") or {}
            fmt = text_cfg.get("format") if isinstance(text_cfg, dict) else None
            self.assertIsInstance(fmt, dict)
            self.assertEqual(fmt.get("type"), "json_schema")
            self.assertEqual(fmt.get("name"), "TestSchema")
            self.assertEqual(fmt.get("schema"), {"type": "object", "properties": {"x": {"type": "string"}}})
            self.assertEqual(fmt.get("strict"), True)

            self.assertEqual(payload.get("reasoning"), {"effort": "medium"})

            return httpx.Response(200, json={"output_text": "pong", "status": "completed"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_responses",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12},
                    timeout_seconds=30,
                    extra={
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "TestSchema",
                                "schema": {"type": "object", "properties": {"x": {"type": "string"}}},
                                "strict": True,
                            },
                        },
                        "reasoning_effort": "medium",
                    },
                )

        self.assertEqual(result.text, "pong")
        self.assertEqual(result.finish_reason, "completed")
        self.assertGreaterEqual(len(seen_payloads), 1)

    def test_drops_text_config_on_400_and_retries(self) -> None:
        seen_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(payload)
            if "text" in payload:
                return httpx.Response(400, json={"error": {"message": "text unsupported"}})
            return httpx.Response(200, json={"output_text": "pong", "status": "completed"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_responses",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12},
                    timeout_seconds=30,
                    extra={
                        "text": {"format": {"type": "json_schema", "name": "x", "schema": {"type": "object"}}},
                    },
                )

        self.assertEqual(result.text, "pong")
        self.assertGreaterEqual(len(seen_payloads), 2)
        self.assertIn("text", seen_payloads[0])
        self.assertNotIn("text", seen_payloads[-1])
        self.assertIn("text", result.dropped_params)


if __name__ == "__main__":
    unittest.main()

