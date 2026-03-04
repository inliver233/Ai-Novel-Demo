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
            self.assertEqual(text_cfg.get("verbosity"), "low")

            self.assertEqual(payload.get("reasoning"), {"effort": "medium"})
            self.assertNotIn("verbosity", payload)

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
                        "verbosity": "low",
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

    def test_appends_v1_on_404_and_retries(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/openai/responses"):
                return httpx.Response(404, json={"error": {"message": "not found"}})
            return httpx.Response(200, json={"output_text": "pong", "status": "completed"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_responses_compatible",
                    base_url="http://stubbed-openai.local/openai",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")
        self.assertGreaterEqual(len(seen_paths), 2)
        self.assertEqual(seen_paths[0], "/openai/responses")
        self.assertEqual(seen_paths[-1], "/openai/v1/responses")

    def test_compatible_falls_back_to_chat_completions_when_responses_rejected(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/responses"):
                return httpx.Response(400, json={"error": {"message": "responses unsupported"}})
            if request.url.path.endswith("/chat/completions"):
                return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]})
            return httpx.Response(404, json={"error": {"message": "not found"}})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_responses_compatible",
                    base_url="http://stubbed-openai.local/openai",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")
        self.assertTrue(any(path.endswith("/responses") for path in seen_paths))
        self.assertTrue(any(path.endswith("/chat/completions") for path in seen_paths))

    def test_compatible_retries_via_stream_when_gateway_requires_stream(self) -> None:
        seen_accepts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            accept = request.headers.get("Accept") or ""
            seen_accepts.append(accept)
            if accept == "application/json":
                return httpx.Response(400, json={"detail": "Stream must be set to true"})

            sse = "\n".join(
                [
                    "event: response.output_text.delta",
                    'data: {"type":"response.output_text.delta","delta":"pong"}',
                    "event: response.completed",
                    'data: {"type":"response.completed","response":{"status":"completed"}}',
                    "data: [DONE]",
                    "",
                ]
            ).encode("utf-8")
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_responses_compatible",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")
        self.assertIn("application/json", seen_accepts)
        self.assertIn("text/event-stream", seen_accepts)

    def test_compatible_stream_input_excludes_system_role_items(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            accept = request.headers.get("Accept") or ""

            if accept == "application/json":
                return httpx.Response(400, json={"detail": "Input must be a list"})

            input_value = payload.get("input")
            if isinstance(input_value, str):
                return httpx.Response(400, json={"detail": "Input must be a list"})

            self.assertIsInstance(payload.get("instructions"), str)
            self.assertIsInstance(input_value, list)
            for item in input_value:
                if isinstance(item, dict) and item.get("role") == "system":
                    self.fail("input must not contain system role items for compatible gateways")

            sse = "\n".join(
                [
                    "event: response.output_text.delta",
                    'data: {"type":"response.output_text.delta","delta":"pong"}',
                    "event: response.completed",
                    'data: {"type":"response.completed","response":{"status":"completed"}}',
                    "data: [DONE]",
                    "",
                ]
            ).encode("utf-8")
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                result = call_llm_messages(
                    provider="openai_responses_compatible",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12},
                    timeout_seconds=30,
                    extra={},
                )

        self.assertEqual(result.text, "pong")


if __name__ == "__main__":
    unittest.main()
