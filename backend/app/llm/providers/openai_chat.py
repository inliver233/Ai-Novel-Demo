from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.llm.max_tokens import extract_max_tokens_upper_bound
from app.llm.openai_extract import (
    extract_openai_finish_reason,
    extract_openai_like_text,
    extract_openai_stream_delta_text,
)
from app.llm.openai_messages import openai_messages_from_list
from app.llm.redaction import redact_text
from app.llm.types import LLMCallResult, LLMStreamState
from app.llm.upstream_errors import map_upstream_error


def _looks_like_messages_unsupported(upstream_text: str | None) -> bool:
    if not upstream_text:
        return False
    normalized = upstream_text.lower()
    return "unsupported parameter: messages" in normalized


def _clamp_payload_max_tokens(payload: dict[str, Any], *, limit: int, compat_adjustments: list[str]) -> bool:
    for key in ("max_tokens", "max_completion_tokens"):
        current = payload.get(key)
        if not isinstance(current, int):
            continue
        if current <= limit:
            continue
        payload[key] = limit
        compat_adjustments.append(f"clamp_max_tokens_{limit}")
        return True
    return False


def _build_openai_compat_downgrade_steps(
    *,
    provider: str,
    payload: dict[str, Any],
    messages: list,
    compat_dropped_params: list[str],
    compat_adjustments: list[str],
) -> list[Callable[[], bool]]:
    def drop_param(name: str) -> bool:
        if name not in payload:
            return False
        payload.pop(name, None)
        compat_dropped_params.append(name)
        compat_adjustments.append(f"drop_{name}")
        return True

    def clamp_max_tokens(limit: int) -> bool:
        return _clamp_payload_max_tokens(payload, limit=limit, compat_adjustments=compat_adjustments)

    def use_max_completion_tokens() -> bool:
        if provider not in ("openai", "openai_compatible"):
            return False
        if "max_tokens" not in payload:
            return False
        if "max_completion_tokens" in payload:
            return False
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        compat_adjustments.append("use_max_completion_tokens")
        return True

    def merge_system_into_user() -> bool:
        payload["messages"] = openai_messages_from_list(messages=messages, merge_system_into_user=True)
        compat_adjustments.append("merge_system_into_user")
        return True

    return [
        lambda: drop_param("response_format"),
        lambda: drop_param("reasoning_effort"),
        lambda: drop_param("seed"),
        lambda: drop_param("logit_bias"),
        lambda: drop_param("stop"),
        lambda: drop_param("top_p"),
        lambda: drop_param("temperature"),
        use_max_completion_tokens,
        lambda: clamp_max_tokens(16384),
        lambda: clamp_max_tokens(8192),
        lambda: clamp_max_tokens(4096),
        lambda: clamp_max_tokens(1024),
        lambda: drop_param("max_tokens"),
        lambda: drop_param("max_completion_tokens"),
        merge_system_into_user,
    ]


def call_openai_chat_completions(
    *,
    client: httpx.Client,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    messages: list,
    filtered_params: dict[str, Any],
    dropped_params: list[str],
    timeout: httpx.Timeout,
    start: float,
    extra: dict[str, Any] | None = None,
) -> LLMCallResult:
    normalized_base_url = (base_url or "").strip().rstrip("/")
    endpoints = [f"{normalized_base_url}/chat/completions"]
    if not normalized_base_url.endswith("/v1"):
        endpoints.append(f"{normalized_base_url}/v1/chat/completions")
    endpoint_idx = 0
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []
    payload: dict[str, Any] = {
        "model": model,
        "messages": openai_messages_from_list(messages=messages, merge_system_into_user=False),
        **filtered_params,
    }
    if extra:
        response_format = extra.get("response_format") or extra.get("responseFormat")
        if isinstance(response_format, dict):
            payload["response_format"] = response_format
        reasoning_effort = extra.get("reasoning_effort") or extra.get("reasoningEffort")
        if isinstance(reasoning_effort, str) and reasoning_effort.strip():
            payload["reasoning_effort"] = reasoning_effort.strip()
        seed = extra.get("seed")
        if isinstance(seed, int):
            payload["seed"] = seed
        logit_bias = extra.get("logit_bias") or extra.get("logitBias")
        if isinstance(logit_bias, dict):
            payload["logit_bias"] = logit_bias
        max_completion_tokens = extra.get("max_completion_tokens") or extra.get("maxCompletionTokens")
        if isinstance(max_completion_tokens, int):
            payload["max_completion_tokens"] = max_completion_tokens
            payload.pop("max_tokens", None)

    def post_openai(payload_obj: dict[str, Any]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"}
        if provider.endswith("_compatible"):
            headers["x-api-key"] = api_key
        return client.post(
            endpoints[endpoint_idx],
            headers=headers,
            json=payload_obj,
            timeout=timeout,
        )

    resp = post_openai(payload)
    if resp.status_code == 404 and endpoint_idx == 0 and len(endpoints) > 1:
        endpoint_idx = 1
        compat_adjustments.append("append_v1_base_url")
        resp = post_openai(payload)
    if provider in ("openai", "openai_compatible") and resp.status_code in (400, 422):
        upper = extract_max_tokens_upper_bound(redact_text(resp.text))
        if upper is not None and _clamp_payload_max_tokens(payload, limit=upper, compat_adjustments=compat_adjustments):
            resp = post_openai(payload)

        # Some gateways/models reject otherwise-valid OpenAI params or roles.
        # Apply a short, deterministic downgrade sequence.
        downgrade_steps = _build_openai_compat_downgrade_steps(
            provider=provider,
            payload=payload,
            messages=messages,
            compat_dropped_params=compat_dropped_params,
            compat_adjustments=compat_adjustments,
        )

        for apply in downgrade_steps:
            if resp.status_code not in (400, 422):
                break
            changed = apply()
            if not changed:
                continue
            resp = post_openai(payload)

    latency_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code // 100 != 2:
        if (
            provider in ("openai", "openai_compatible")
            and resp.status_code in (400, 422)
            and _looks_like_messages_unsupported(resp.text)
            and not (extra or {}).get("_internal_from_responses_fallback")
        ):
            from app.llm.providers.openai_responses import call_openai_responses

            merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
            fallback_provider = "openai_responses_compatible" if provider == "openai_compatible" else "openai_responses"
            fallback_extra = dict(extra or {})
            fallback_extra["_internal_from_chat_fallback"] = True
            return call_openai_responses(
                client=client,
                provider=fallback_provider,
                base_url=base_url,
                model=model,
                api_key=api_key,
                messages=messages,
                filtered_params=filtered_params,
                dropped_params=merged_dropped,
                timeout=timeout,
                start=start,
                extra=fallback_extra,
            )

        extra_details = None
        if compat_adjustments:
            extra_details = {
                "compat_adjustments": compat_adjustments,
                "compat_dropped_params": sorted(set(compat_dropped_params)),
            }
        raise map_upstream_error(resp.status_code, redact_text(resp.text), extra_details=extra_details)
    data = resp.json()
    text = extract_openai_like_text(data)
    finish_reason = extract_openai_finish_reason(data)
    if text is None:
        details: dict[str, Any] = {}
        if settings.app_env == "dev":
            details["upstream_response"] = redact_text(resp.text)[:500]
        raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应格式不兼容，无法解析输出文本", status_code=502, details=details)
    merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
    return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=merged_dropped, finish_reason=finish_reason)


def call_openai_chat_completions_stream(
    *,
    client: httpx.Client,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    messages: list,
    filtered_params: dict[str, Any],
    dropped_params: list[str],
    timeout: httpx.Timeout,
    start: float,
    extra: dict[str, Any] | None = None,
) -> tuple[Iterator[str], LLMStreamState]:
    normalized_base_url = (base_url or "").strip().rstrip("/")
    endpoints = [f"{normalized_base_url}/chat/completions"]
    if not normalized_base_url.endswith("/v1"):
        endpoints.append(f"{normalized_base_url}/v1/chat/completions")
    endpoint_idx = 0
    state = LLMStreamState(dropped_params=dropped_params)
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []
    payload: dict[str, Any] = {
        "model": model,
        "messages": openai_messages_from_list(messages=messages, merge_system_into_user=False),
        **filtered_params,
        "stream": True,
    }
    if extra:
        response_format = extra.get("response_format") or extra.get("responseFormat")
        if isinstance(response_format, dict):
            payload["response_format"] = response_format
        reasoning_effort = extra.get("reasoning_effort") or extra.get("reasoningEffort")
        if isinstance(reasoning_effort, str) and reasoning_effort.strip():
            payload["reasoning_effort"] = reasoning_effort.strip()
        seed = extra.get("seed")
        if isinstance(seed, int):
            payload["seed"] = seed
        logit_bias = extra.get("logit_bias") or extra.get("logitBias")
        if isinstance(logit_bias, dict):
            payload["logit_bias"] = logit_bias
        max_completion_tokens = extra.get("max_completion_tokens") or extra.get("maxCompletionTokens")
        if isinstance(max_completion_tokens, int):
            payload["max_completion_tokens"] = max_completion_tokens
            payload.pop("max_tokens", None)

    def _open_stream(payload_obj: dict[str, Any]) -> httpx._client.StreamContextManager[httpx.Response]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if provider.endswith("_compatible"):
            headers["x-api-key"] = api_key
        return client.stream(
            "POST",
            endpoints[endpoint_idx],
            headers=headers,
            json=payload_obj,
            timeout=timeout,
        )

    downgrade_steps = _build_openai_compat_downgrade_steps(
        provider=provider,
        payload=payload,
        messages=messages,
        compat_dropped_params=compat_dropped_params,
        compat_adjustments=compat_adjustments,
    )

    def generator() -> Iterator[str]:
        nonlocal endpoint_idx
        cm: httpx._client.StreamContextManager[httpx.Response] | None = None
        resp: httpx.Response | None = None
        upstream_text: str | None = None
        used_responses_fallback = False
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

                if status_code == 404 and endpoint_idx == 0 and len(endpoints) > 1:
                    endpoint_idx = 1
                    compat_adjustments.append("append_v1_base_url")
                    continue

                if provider in ("openai", "openai_compatible") and status_code in (400, 422) and attempts <= (len(downgrade_steps) + 1):
                    upper = extract_max_tokens_upper_bound(redact_text(upstream_text or ""))
                    if upper is not None and _clamp_payload_max_tokens(payload, limit=upper, compat_adjustments=compat_adjustments):
                        continue

                    changed = False
                    for step in downgrade_steps:
                        if step():
                            changed = True
                            break
                    if changed:
                        continue

                if (
                    provider in ("openai", "openai_compatible")
                    and status_code in (400, 422)
                    and _looks_like_messages_unsupported(upstream_text or "")
                    and not (extra or {}).get("_internal_from_responses_fallback")
                ):
                    from app.llm.providers.openai_responses import call_openai_responses_stream

                    used_responses_fallback = True
                    merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
                    fallback_provider = "openai_responses_compatible" if provider == "openai_compatible" else "openai_responses"
                    fallback_extra = dict(extra or {})
                    fallback_extra["_internal_from_chat_fallback"] = True
                    fallback_iter, fallback_state = call_openai_responses_stream(
                        client=client,
                        provider=fallback_provider,
                        base_url=base_url,
                        model=model,
                        api_key=api_key,
                        messages=messages,
                        filtered_params=filtered_params,
                        dropped_params=merged_dropped,
                        timeout=timeout,
                        start=start,
                        extra=fallback_extra,
                    )
                    for chunk in fallback_iter:
                        yield chunk
                    state.finish_reason = fallback_state.finish_reason
                    state.latency_ms = fallback_state.latency_ms
                    state.dropped_params = fallback_state.dropped_params
                    return

                extra_details = None
                if compat_adjustments:
                    extra_details = {
                        "compat_adjustments": compat_adjustments,
                        "compat_dropped_params": sorted(set(compat_dropped_params)),
                    }
                raise map_upstream_error(status_code, redact_text(upstream_text or ""), extra_details=extra_details)

            if resp is None:
                raise AppError(code="LLM_UPSTREAM_ERROR", message="模型服务异常，请稍后重试", status_code=502)

            for line in resp.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="ignore")
                line = str(line).strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                delta = extract_openai_stream_delta_text(data)
                if delta:
                    yield delta

                finish_reason = extract_openai_finish_reason(data)
                if finish_reason:
                    state.finish_reason = finish_reason
        except httpx.TimeoutException as exc:
            raise AppError(code="LLM_TIMEOUT", message="连接超时，请检查网络或 base_url 是否正确", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError(code="LLM_UPSTREAM_ERROR", message="连接失败，请检查网络或 base_url 是否正确", status_code=502) from exc
        finally:
            if not used_responses_fallback:
                state.latency_ms = int((time.perf_counter() - start) * 1000)
                merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
                state.dropped_params = merged_dropped
            if cm is not None:
                cm.__exit__(None, None, None)

    return generator(), state
