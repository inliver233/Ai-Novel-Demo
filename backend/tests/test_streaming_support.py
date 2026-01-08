import json
import unittest
from unittest.mock import patch

import httpx

from app.llm.client import call_llm_stream_messages
from app.llm.messages import ChatMessage


class TestStreamingSupport(unittest.TestCase):
    def test_openai_chat_stream_accepts_responses_delta_events(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/chat/completions"))
            sse = "\n".join(
                [
                    'data: {"type":"response.output_text.delta","delta":"pong"}',
                    "data: [DONE]",
                    "",
                ]
            ).encode("utf-8")
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                stream_iter, state = call_llm_stream_messages(
                    provider="openai_compatible",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={},
                    timeout_seconds=30,
                    extra={},
                )
                text = "".join(list(stream_iter))

        self.assertEqual(text, "pong")
        self.assertIsNotNone(state.latency_ms)

    def test_openai_chat_stream_falls_back_to_responses_when_messages_unsupported(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/chat/completions"):
                return httpx.Response(400, json={"detail": "Unsupported parameter: messages"})
            if request.url.path.endswith("/responses"):
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
            return httpx.Response(404, json={"error": {"message": "not found"}})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                stream_iter, state = call_llm_stream_messages(
                    provider="openai_compatible",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={},
                    timeout_seconds=30,
                    extra={},
                )
                text = "".join(list(stream_iter))

        self.assertEqual(text, "pong")
        self.assertEqual(state.finish_reason, "completed")
        self.assertIsNotNone(state.latency_ms)
        self.assertTrue(any(path.endswith("/chat/completions") for path in seen_paths))
        self.assertTrue(any(path.endswith("/responses") for path in seen_paths))

    def test_openai_responses_stream_parses_delta_and_finish_reason(self) -> None:
        seen_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/responses"))
            payload = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(payload)
            self.assertTrue(payload.get("stream"))
            self.assertIn("max_output_tokens", payload)

            sse = "\n".join(
                [
                    "event: response.output_text.delta",
                    'data: {"type":"response.output_text.delta","delta":"pon"}',
                    'data: {"type":"response.output_text.delta","delta":"g"}',
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
                stream_iter, state = call_llm_stream_messages(
                    provider="openai_responses",
                    base_url="http://stubbed-openai.local/v1",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 12},
                    timeout_seconds=30,
                    extra={},
                )
                text = "".join(list(stream_iter))

        self.assertEqual(text, "pong")
        self.assertEqual(state.finish_reason, "completed")
        self.assertIsNotNone(state.latency_ms)
        self.assertGreaterEqual(len(seen_payloads), 1)

    def test_openai_responses_compatible_stream_falls_back_to_chat_completions(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/responses"):
                return httpx.Response(400, json={"error": {"message": "responses unsupported"}})
            if request.url.path.endswith("/chat/completions"):
                sse = "\n".join(
                    [
                        'data: {"choices":[{"delta":{"content":"pong"}}]}',
                        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                        "data: [DONE]",
                        "",
                    ]
                ).encode("utf-8")
                return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})
            return httpx.Response(404, json={"error": {"message": "not found"}})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                stream_iter, state = call_llm_stream_messages(
                    provider="openai_responses_compatible",
                    base_url="http://stubbed-openai.local/openai",
                    model="gpt-test",
                    api_key="sk-test-SECRET1234",
                    messages=[ChatMessage(role="user", content="hi")],
                    params={},
                    timeout_seconds=30,
                    extra={},
                )
                text = "".join(list(stream_iter))

        self.assertEqual(text, "pong")
        self.assertEqual(state.finish_reason, "stop")
        self.assertIsNotNone(state.latency_ms)
        self.assertTrue(any(path.endswith("/responses") for path in seen_paths))
        self.assertTrue(any(path.endswith("/chat/completions") for path in seen_paths))

    def test_anthropic_stream_parses_text_and_finish_reason(self) -> None:
        api_key = "anthropic-test-SECRET1234"

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/v1/messages"))
            self.assertEqual(request.headers.get("x-api-key"), api_key)
            self.assertEqual(request.headers.get("anthropic-version"), "2023-06-01")
            self.assertEqual(request.headers.get("anthropic-beta"), "test-beta-1")

            payload = json.loads(request.content.decode("utf-8"))
            self.assertTrue(payload.get("stream"))
            self.assertEqual(payload.get("thinking"), {"type": "enabled", "budget_tokens": 256})

            sse = "\n".join(
                [
                    'event: content_block_delta',
                    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"pong"}}',
                    'event: message_delta',
                    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
                    "event: message_stop",
                    'data: {"type":"message_stop"}',
                    "",
                ]
            ).encode("utf-8")
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                stream_iter, state = call_llm_stream_messages(
                    provider="anthropic",
                    base_url="http://stubbed-anthropic.local",
                    model="claude-test",
                    api_key=api_key,
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 64},
                    timeout_seconds=30,
                    extra={
                        "anthropic_version": "2023-06-01",
                        "anthropic_beta": "test-beta-1",
                        "thinking": {"type": "enabled", "budget_tokens": 256},
                    },
                )
                text = "".join(list(stream_iter))

        self.assertEqual(text, "pong")
        self.assertEqual(state.finish_reason, "end_turn")
        self.assertIsNotNone(state.latency_ms)

    def test_gemini_stream_parses_cumulative_text_as_delta(self) -> None:
        api_key = "gemini-test-SECRET1234"

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith(":streamGenerateContent"))
            self.assertEqual(request.url.query, b"alt=sse")
            self.assertNotIn("key", request.url.params)
            self.assertEqual(request.headers.get("x-goog-api-key"), api_key)

            payload = json.loads(request.content.decode("utf-8"))
            self.assertEqual(payload.get("generationConfig", {}).get("thinkingConfig"), {"thinkingBudget": 128})

            sse = "\n".join(
                [
                    'data: {"candidates":[{"content":{"parts":[{"text":"pon"}]}}]}',
                    'data: {"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":"pong"}]}}]}',
                    "data: [DONE]",
                    "",
                ]
            ).encode("utf-8")
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with patch("app.llm.client.get_llm_http_client", return_value=client):
                stream_iter, state = call_llm_stream_messages(
                    provider="gemini",
                    base_url="http://stubbed-gemini.local",
                    model="gemini-test",
                    api_key=api_key,
                    messages=[ChatMessage(role="user", content="hi")],
                    params={"max_tokens": 64},
                    timeout_seconds=30,
                    extra={"thinkingConfig": {"thinkingBudget": 128}},
                )
                text = "".join(list(stream_iter))

        self.assertEqual(text, "pong")
        self.assertEqual(state.finish_reason, "STOP")
        self.assertIsNotNone(state.latency_ms)


if __name__ == "__main__":
    unittest.main()
