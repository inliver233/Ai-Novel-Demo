from __future__ import annotations

import time
from typing import Any

import httpx

from app.llm.redaction import redact_text
from app.llm.messages import ChatMessage, coalesce_system, merge_consecutive, normalize_role
from app.llm.types import LLMCallResult
from app.llm.upstream_errors import map_upstream_error


def call_gemini_generate_content(
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
    endpoint = f"{base_url}/v1beta/models/{model}:generateContent"
    url = endpoint

    generation_config: dict[str, Any] = {}
    if "temperature" in filtered_params:
        generation_config["temperature"] = filtered_params["temperature"]
    if "top_p" in filtered_params:
        generation_config["topP"] = filtered_params["top_p"]
    if "max_tokens" in filtered_params:
        generation_config["maxOutputTokens"] = filtered_params["max_tokens"]
    if "top_k" in filtered_params:
        generation_config["topK"] = filtered_params["top_k"]
    if "stop" in filtered_params:
        generation_config["stopSequences"] = filtered_params["stop"]

    normalized = merge_consecutive(messages)
    system, non_system = coalesce_system(normalized)

    contents: list[dict[str, Any]] = []
    for msg in non_system:
        role = normalize_role(msg.role)
        content = msg.content
        if role == "assistant":
            gemini_role = "model"
        elif role == "user":
            gemini_role = "user"
        else:
            gemini_role = "user"
            content = f"[{role.upper()}]\n{content}"
        contents.append({"role": gemini_role, "parts": [{"text": content}]})
    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]

    payload: dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
    if system.strip():
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    safety = extra.get("safety_settings") or extra.get("safetySettings")
    if safety is not None:
        payload["safetySettings"] = safety

    resp = client.post(
        url,
        headers={"Content-Type": "application/json", "Accept": "application/json", "x-goog-api-key": api_key},
        json=payload,
        timeout=timeout,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code // 100 != 2:
        raise map_upstream_error(resp.status_code, redact_text(resp.text))
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return LLMCallResult(text="", latency_ms=latency_ms, dropped_params=dropped_params, finish_reason=None)
    finish_reason = candidates[0].get("finishReason") if isinstance(candidates[0], dict) else None
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
    text = "".join(text_parts)
    return LLMCallResult(
        text=text,
        latency_ms=latency_ms,
        dropped_params=dropped_params,
        finish_reason=str(finish_reason) if isinstance(finish_reason, str) else None,
    )
