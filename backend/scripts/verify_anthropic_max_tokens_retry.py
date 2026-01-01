from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.client import call_llm_messages
from app.llm.messages import ChatMessage


def main() -> None:
    seen_max_tokens: list[int | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/v1/messages")

        payload = json.loads(request.content.decode("utf-8"))
        max_tokens = payload.get("max_tokens")
        seen_max_tokens.append(max_tokens)

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
    client = httpx.Client(transport=transport)

    import app.llm.client as llm_client_module

    original_factory = llm_client_module.get_llm_http_client
    llm_client_module.get_llm_http_client = lambda: client
    try:
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
    finally:
        llm_client_module.get_llm_http_client = original_factory
        client.close()

    assert result.text.strip() == "pong"
    assert len(seen_max_tokens) >= 2, f"expected retry on 400/422, got calls={len(seen_max_tokens)}"
    assert seen_max_tokens[0] == 200000, f"expected first call max_tokens=200000, got {seen_max_tokens[0]}"
    assert seen_max_tokens[1] == 196608, f"expected clamp to 196608 (from upstream), got {seen_max_tokens[1]}"

    print("PASS: anthropic max_tokens compat retry works")


if __name__ == "__main__":
    main()
