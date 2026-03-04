from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator

import httpx

from app.core.errors import AppError
from app.llm.max_tokens import extract_max_tokens_upper_bound
from app.llm.messages import ChatMessage, coalesce_system, merge_consecutive, normalize_role
from app.llm.redaction import redact_text
from app.llm.types import LLMCallResult, LLMStreamState
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
    anthropic_beta = extra.get("anthropic_beta") or extra.get("anthropicBeta")
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
    thinking = extra.get("thinking")
    if isinstance(thinking, dict):
        payload["thinking"] = thinking
    payload = {k: v for k, v in payload.items() if v is not None}
    compat_adjustments: list[str] = []

    def _build_headers() -> dict[str, str]:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": str(anthropic_version),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if anthropic_beta:
            if isinstance(anthropic_beta, str) and anthropic_beta.strip():
                headers["anthropic-beta"] = anthropic_beta.strip()
            elif isinstance(anthropic_beta, list):
                parts = [str(p).strip() for p in anthropic_beta if str(p).strip()]
                if parts:
                    headers["anthropic-beta"] = ",".join(parts)
        return headers

    def post_anthropic(payload_obj: dict[str, Any]) -> httpx.Response:
        return client.post(
            endpoint,
            headers=_build_headers(),
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
            lambda: drop_payload_param("thinking"),
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


def call_anthropic_messages_stream(
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
) -> tuple[Iterator[str], LLMStreamState]:
    endpoint = f"{base_url}/v1/messages"
    anthropic_version = extra.get("anthropic_version") or extra.get("anthropicVersion") or "2023-06-01"
    anthropic_beta = extra.get("anthropic_beta") or extra.get("anthropicBeta")
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

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": filtered_params.get("temperature"),
        "top_p": filtered_params.get("top_p"),
        "top_k": filtered_params.get("top_k"),
        "stop_sequences": filtered_params.get("stop"),
        "system": system_prompt,
        "messages": anthropic_messages,
        "stream": True,
    }
    thinking = extra.get("thinking")
    if isinstance(thinking, dict):
        payload["thinking"] = thinking
    payload = {k: v for k, v in payload.items() if v is not None}

    state = LLMStreamState(dropped_params=dropped_params)
    compat_adjustments: list[str] = []
    compat_dropped_params: list[str] = []

    def _build_headers() -> dict[str, str]:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": str(anthropic_version),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if anthropic_beta:
            if isinstance(anthropic_beta, str) and anthropic_beta.strip():
                headers["anthropic-beta"] = anthropic_beta.strip()
            elif isinstance(anthropic_beta, list):
                parts = [str(p).strip() for p in anthropic_beta if str(p).strip()]
                if parts:
                    headers["anthropic-beta"] = ",".join(parts)
        return headers

    def _open_stream(payload_obj: dict[str, Any]) -> httpx._client.StreamContextManager[httpx.Response]:
        return client.stream("POST", endpoint, headers=_build_headers(), json=payload_obj, timeout=timeout)

    def drop_payload_param(name: str) -> bool:
        if name not in payload:
            return False
        payload.pop(name, None)
        compat_dropped_params.append(name)
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

    downgrade_steps: list[Callable[[], bool]] = [
        lambda: clamp_max_tokens(16384),
        lambda: clamp_max_tokens(8192),
        lambda: clamp_max_tokens(4096),
        lambda: clamp_max_tokens(1024),
        lambda: drop_payload_param("thinking"),
        lambda: drop_payload_param("stop_sequences"),
        lambda: drop_payload_param("top_k"),
        lambda: drop_payload_param("top_p"),
        lambda: drop_payload_param("temperature"),
    ]

    def generator() -> Iterator[str]:
        cm: httpx._client.StreamContextManager[httpx.Response] | None = None
        resp: httpx.Response | None = None
        upstream_text: str | None = None
        try:
            attempts = 0
            while True:
                attempts += 1
                if cm is not None:
                    cm.__exit__(None, None, None)
                    cm = None
                    resp = None

                cm = _open_stream(payload)
                resp = cm.__enter__()
                if resp.status_code // 100 == 2:
                    break

                try:
                    upstream_text = resp.read().decode("utf-8", errors="ignore")
                except Exception:
                    upstream_text = None
                status_code = resp.status_code
                cm.__exit__(None, None, None)
                cm = None
                resp = None

                if status_code in (400, 422) and attempts <= (len(downgrade_steps) + 1):
                    upper = extract_max_tokens_upper_bound(redact_text(upstream_text or ""))
                    if upper is not None and clamp_max_tokens(upper):
                        continue
                    changed = False
                    for step in downgrade_steps:
                        if step():
                            changed = True
                            break
                    if changed:
                        continue

                extra_details = {"compat_adjustments": compat_adjustments} if compat_adjustments else None
                raise map_upstream_error(status_code, redact_text(upstream_text or ""), extra_details=extra_details)

            if resp is None:
                raise AppError(code="LLM_UPSTREAM_ERROR", message="模型服务异常，请稍后重试", status_code=502)

            current_event: str | None = None
            for line in resp.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="ignore")
                line = str(line).strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line[6:].strip() or None
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type") if isinstance(data, dict) else None
                if not isinstance(event_type, str):
                    event_type = current_event or ""

                if event_type == "content_block_delta" and isinstance(data, dict):
                    delta_obj = data.get("delta")
                    if isinstance(delta_obj, dict) and delta_obj.get("type") == "text_delta" and isinstance(delta_obj.get("text"), str):
                        yield delta_obj["text"]
                    continue

                if event_type == "message_delta" and isinstance(data, dict):
                    delta_obj = data.get("delta")
                    if isinstance(delta_obj, dict) and isinstance(delta_obj.get("stop_reason"), str):
                        state.finish_reason = delta_obj.get("stop_reason") or None
                    continue

                if event_type == "message_stop":
                    break

                if event_type == "error" and isinstance(data, dict):
                    err_obj = data.get("error")
                    if isinstance(err_obj, dict):
                        msg = err_obj.get("message")
                        if isinstance(msg, str) and msg.strip():
                            raise AppError(code="LLM_UPSTREAM_ERROR", message=msg.strip(), status_code=502)
                    raise AppError(code="LLM_UPSTREAM_ERROR", message="模型服务异常，请稍后重试", status_code=502)
        except httpx.TimeoutException as exc:
            raise AppError(code="LLM_TIMEOUT", message="连接超时，请检查网络或 base_url 是否正确", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError(code="LLM_UPSTREAM_ERROR", message="连接失败，请检查网络或 base_url 是否正确", status_code=502) from exc
        finally:
            state.latency_ms = int((time.perf_counter() - start) * 1000)
            merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
            state.dropped_params = merged_dropped
            if cm is not None:
                cm.__exit__(None, None, None)

    return generator(), state
