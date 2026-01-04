from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app.llm.max_tokens import extract_max_tokens_upper_bound
from app.llm.messages import ChatMessage, coalesce_system, merge_consecutive, normalize_role
from app.llm.redaction import redact_text
from app.llm.types import LLMCallResult
from app.llm.upstream_errors import map_upstream_error


def call_anthropic_messages(
    *,
    client: httpx.Client,
    base_url: str,
    model: str,
    api_key: str,
    messages: list[ChatMessage],
    filtered_params: dict[str, Any],
    dropped_params: list[str],
    timeout: httpx.Timeout,
    start: float,
    extra: dict[str, Any],
) -> LLMCallResult:
    endpoint = f"{base_url}/v1/messages"
    anthropic_version = extra.get("anthropic_version") or extra.get("anthropicVersion") or "2023-06-01"
    max_tokens = int(filtered_params.get("max_tokens") or 1500)

    normalized = merge_consecutive(messages)
    system, non_system = coalesce_system(normalized)
    system_prompt = system if system.strip() else None

    anthropic_messages: list[dict[str, Any]] = []
    for msg in non_system:
        role = normalize_role(msg.role)
        content = msg.content
        if role not in ("user", "assistant"):
            role = "user"
            content = f"[{msg.role.upper()}]\n{content}"
        anthropic_messages.append({"role": role, "content": content})

    if not anthropic_messages:
        anthropic_messages = [{"role": "user", "content": ""}]
    if anthropic_messages and anthropic_messages[0].get("role") != "user":
        anthropic_messages.insert(0, {"role": "user", "content": ""})

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": filtered_params.get("temperature"),
        "top_p": filtered_params.get("top_p"),
        "top_k": filtered_params.get("top_k"),
        "stop_sequences": filtered_params.get("stop"),
        "system": system_prompt,
        "messages": anthropic_messages,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    compat_adjustments: list[str] = []

    def post_anthropic(payload_obj: dict[str, Any]) -> httpx.Response:
        return client.post(
            endpoint,
            headers={
                "x-api-key": api_key,
                "anthropic-version": str(anthropic_version),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload_obj,
            timeout=timeout,
        )

    def drop_payload_param(name: str) -> bool:
        if name not in payload:
            return False
        payload.pop(name, None)
        compat_adjustments.append(f"drop_{name}")
        return True

    def clamp_max_tokens(limit: int) -> bool:
        current = payload.get("max_tokens")
        if not isinstance(current, int):
            return False
        if current <= limit:
            return False
        payload["max_tokens"] = limit
        compat_adjustments.append(f"clamp_max_tokens_{limit}")
        return True

    def clamp_max_tokens_from_error() -> bool:
        limit = extract_max_tokens_upper_bound(redact_text(resp.text))
        if limit is None:
            return False
        return clamp_max_tokens(limit)

    resp = post_anthropic(payload)
    if resp.status_code in (400, 422):
        downgrade_steps: list[Callable[[], bool]] = [
            clamp_max_tokens_from_error,
            lambda: clamp_max_tokens(16384),
            lambda: clamp_max_tokens(8192),
            lambda: clamp_max_tokens(4096),
            lambda: clamp_max_tokens(1024),
            lambda: drop_payload_param("stop_sequences"),
            lambda: drop_payload_param("top_k"),
            lambda: drop_payload_param("top_p"),
            lambda: drop_payload_param("temperature"),
        ]
        for apply in downgrade_steps:
            if resp.status_code not in (400, 422):
                break
            changed = apply()
            if not changed:
                continue
            resp = post_anthropic(payload)

    latency_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code // 100 != 2:
        extra_details = {"compat_adjustments": compat_adjustments} if compat_adjustments else None
        raise map_upstream_error(resp.status_code, redact_text(resp.text), extra_details=extra_details)
    data = resp.json()
    finish_reason = data.get("stop_reason") if isinstance(data, dict) else None
    content_obj = data.get("content") if isinstance(data, dict) else None
    if isinstance(content_obj, str):
        text = content_obj.strip()
    elif isinstance(content_obj, list):
        text_parts = [p.get("text", "") for p in content_obj if isinstance(p, dict) and isinstance(p.get("text"), str)]
        text = "".join(text_parts).strip()
    else:
        text = ""
    return LLMCallResult(
        text=text,
        latency_ms=latency_ms,
        dropped_params=dropped_params,
        finish_reason=str(finish_reason) if isinstance(finish_reason, str) else None,
    )

