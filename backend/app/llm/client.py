from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from urllib.parse import urlencode

import httpx

from app.core.errors import AppError
from app.core.config import settings
from app.llm.http_client import get_llm_http_client
from app.llm.messages import ChatMessage, coalesce_system, flatten_messages, merge_consecutive, normalize_role
from app.llm.utils import normalize_base_url


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    text: str
    latency_ms: int
    dropped_params: list[str]
    finish_reason: str | None = None


@dataclass(slots=True)
class LLMStreamState:
    finish_reason: str | None = None
    latency_ms: int | None = None
    dropped_params: list[str] = field(default_factory=list)


def _filter_params(provider: str, params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    supported: set[str]
    if provider == "openai":
        supported = {"temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty", "stop"}
    elif provider == "openai_compatible":
        # Many OpenAI-compatible gateways only support a subset of OpenAI params. Keep this minimal to reduce 400s.
        supported = {"temperature", "top_p", "max_tokens", "stop"}
    elif provider == "anthropic":
        supported = {"temperature", "top_p", "max_tokens", "top_k", "stop"}
    elif provider == "gemini":
        supported = {"temperature", "top_p", "max_tokens", "top_k", "stop"}
    else:
        supported = set()
    filtered: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        if key == "stop" and isinstance(value, list) and not value:
            continue
        if key in supported:
            filtered[key] = value
        else:
            dropped.append(key)
    return filtered, dropped


def _map_upstream_error(
    status_code: int,
    upstream_text: str | None = None,
    extra_details: dict[str, Any] | None = None,
) -> AppError:
    details: dict[str, Any] = {"status_code": status_code}
    if extra_details:
        details.update(extra_details)
    if upstream_text and settings.app_env == "dev":
        details["upstream_error"] = upstream_text[:500]
    if status_code in (401, 403):
        return AppError(code="LLM_AUTH_ERROR", message="API Key 无效或已过期，请检查后重试", status_code=401, details=details)
    if status_code == 429:
        return AppError(code="LLM_RATE_LIMIT", message="请求过多/额度不足，请稍后重试", status_code=429, details=details)
    if status_code in (400, 422):
        return AppError(code="LLM_BAD_REQUEST", message="请求参数有误，可能是模型名称或参数不支持", status_code=400, details=details)
    if status_code == 408 or status_code == 504:
        return AppError(code="LLM_TIMEOUT", message="请求超时，请稍后重试", status_code=504, details=details)
    return AppError(code="LLM_UPSTREAM_ERROR", message="模型服务异常，请稍后重试", status_code=502, details=details)


_MAX_TOKENS_UPPER_BOUND_RE_LIST = [
    re.compile(r"(?i)max(?:_tokens?|\s+tokens?)\s*>\s*(\d{3,})"),
    re.compile(r"(?i)max(?:_tokens?|\s+tokens?)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
    re.compile(r"(?i)max(?:OutputTokens|\s+output\s+tokens?)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
]


def _extract_max_tokens_upper_bound(text: str) -> int | None:
    if not text:
        return None
    candidates: list[str] = [text]
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    if parsed is not None:
        candidates = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                candidates.append(node)
                return
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
                return
            if isinstance(node, list):
                for value in node:
                    walk(value)
                return

        walk(parsed)
        candidates.append(text)

    for candidate in candidates:
        for pattern in _MAX_TOKENS_UPPER_BOUND_RE_LIST:
            match = pattern.search(candidate)
            if not match:
                continue
            try:
                value = int(match.group(1))
            except Exception:
                continue
            if value > 0:
                return value
    return None


def _openai_messages(*, system: str, user: str, merge_system_into_user: bool) -> list[dict[str, Any]]:
    sys = system.strip()
    if merge_system_into_user and sys:
        merged = f"{sys}\n\n{user}"
        return [{"role": "user", "content": merged}]

    messages: list[dict[str, Any]] = []
    if sys:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    return messages


def _openai_messages_from_list(*, messages: list[ChatMessage], merge_system_into_user: bool) -> list[dict[str, Any]]:
    normalized = merge_consecutive(messages)
    system, non_system = coalesce_system(normalized)
    if merge_system_into_user:
        merged_user = flatten_messages(non_system)
        merged = merged_user
        if system.strip():
            merged = f"{system}\n\n{merged_user}" if merged_user.strip() else system
        return [{"role": "user", "content": merged}]

    out: list[dict[str, Any]] = []
    if system.strip():
        out.append({"role": "system", "content": system})
    for msg in non_system:
        role = normalize_role(msg.role)
        payload: dict[str, Any] = {"role": role, "content": msg.content}
        if msg.name:
            payload["name"] = msg.name
        out.append(payload)
    if not out:
        out.append({"role": "user", "content": ""})
    return out


def _extract_openai_like_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                    if parts:
                        return "".join(parts)
            if isinstance(first.get("text"), str):
                return first["text"]
            delta = first.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]

    # OpenAI Responses API (some gateways are "OpenAI-compatible" but return Responses-like shapes)
    output = data.get("output")
    if isinstance(output, list) and output:
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
        if parts:
            return "".join(parts)

    if isinstance(data.get("content"), str):
        return data["content"]

    return None


def _extract_openai_finish_reason(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict) and isinstance(first.get("finish_reason"), str):
            return first["finish_reason"] or None
    if isinstance(data.get("finish_reason"), str):
        return data["finish_reason"] or None
    return None


def _extract_openai_stream_delta_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                    if parts:
                        return "".join(parts)
            if isinstance(first.get("text"), str):
                return first["text"]
    return None


def call_llm_stream(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    system: str,
    user: str,
    params: dict[str, Any],
    timeout_seconds: int,
    extra: dict[str, Any] | None = None,
) -> tuple[Iterator[str], LLMStreamState]:
    if not api_key:
        raise AppError(code="LLM_KEY_MISSING", message="缺少 API Key（请在 Prompts 页填写）", status_code=401)
    if provider not in ("openai", "openai_compatible"):
        raise AppError(code="LLM_STREAM_UNSUPPORTED", message="该 provider 暂不支持流式输出", status_code=400)

    base_url = normalize_base_url(base_url)
    filtered_params, dropped = _filter_params(provider, params)
    extra = extra or {}
    state = LLMStreamState(dropped_params=dropped)

    start = time.perf_counter()
    client = get_llm_http_client()
    read_timeout = max(1.0, float(timeout_seconds))
    connect_timeout = min(10.0, read_timeout)
    write_timeout = min(10.0, read_timeout)
    pool_timeout = min(10.0, read_timeout)
    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=write_timeout, pool=pool_timeout)

    endpoint = f"{base_url}/chat/completions"
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []
    payload: dict[str, Any] = {
        "model": model,
        "messages": _openai_messages(system=system, user=user, merge_system_into_user=False),
        **filtered_params,
        "stream": True,
    }

    def _open_stream(payload_obj: dict[str, Any]) -> httpx._client.StreamContextManager[httpx.Response]:
        return client.stream(
            "POST",
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=payload_obj,
            timeout=timeout,
        )

    def drop_param(name: str) -> bool:
        if name not in payload:
            return False
        payload.pop(name, None)
        compat_dropped_params.append(name)
        compat_adjustments.append(f"drop_{name}")
        return True

    def clamp_max_tokens(limit: int) -> bool:
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

    def use_max_completion_tokens() -> bool:
        if provider != "openai":
            return False
        if "max_tokens" not in payload:
            return False
        if "max_completion_tokens" in payload:
            return False
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        compat_adjustments.append("use_max_completion_tokens")
        return True

    def merge_system_into_user() -> bool:
        if not system.strip():
            return False
        payload["messages"] = _openai_messages(system=system, user=user, merge_system_into_user=True)
        compat_adjustments.append("merge_system_into_user")
        return True

    downgrade_steps: list[Callable[[], bool]] = [
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

                if provider in ("openai", "openai_compatible") and status_code in (400, 422) and attempts <= (len(downgrade_steps) + 1):
                    changed = False
                    for step in downgrade_steps:
                        if step():
                            changed = True
                            break
                    if changed:
                        continue

                extra_details = None
                if compat_adjustments:
                    extra_details = {
                        "compat_adjustments": compat_adjustments,
                        "compat_dropped_params": sorted(set(compat_dropped_params)),
                    }
                raise _map_upstream_error(status_code, _redact(upstream_text or ""), extra_details=extra_details)

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

                delta = _extract_openai_stream_delta_text(data)
                if delta:
                    yield delta

                finish_reason = _extract_openai_finish_reason(data)
                if finish_reason:
                    state.finish_reason = finish_reason
        except httpx.TimeoutException as exc:
            raise AppError(code="LLM_TIMEOUT", message="连接超时，请检查网络或 base_url 是否正确", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError(code="LLM_UPSTREAM_ERROR", message="连接失败，请检查网络或 base_url 是否正确", status_code=502) from exc
        finally:
            state.latency_ms = int((time.perf_counter() - start) * 1000)
            merged_dropped = dropped + [p for p in compat_dropped_params if p not in dropped]
            state.dropped_params = merged_dropped
            if cm is not None:
                cm.__exit__(None, None, None)

    return generator(), state


def call_llm_stream_messages(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    messages: list[ChatMessage],
    params: dict[str, Any],
    timeout_seconds: int,
    extra: dict[str, Any] | None = None,
) -> tuple[Iterator[str], LLMStreamState]:
    if not api_key:
        raise AppError(code="LLM_KEY_MISSING", message="缺少 API Key（请在 Prompts 页填写）", status_code=401)
    if provider not in ("openai", "openai_compatible"):
        raise AppError(code="LLM_STREAM_UNSUPPORTED", message="该 provider 暂不支持流式输出", status_code=400)

    base_url = normalize_base_url(base_url)
    filtered_params, dropped = _filter_params(provider, params)
    extra = extra or {}
    state = LLMStreamState(dropped_params=dropped)

    start = time.perf_counter()
    client = get_llm_http_client()
    read_timeout = max(1.0, float(timeout_seconds))
    connect_timeout = min(10.0, read_timeout)
    write_timeout = min(10.0, read_timeout)
    pool_timeout = min(10.0, read_timeout)
    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=write_timeout, pool=pool_timeout)

    endpoint = f"{base_url}/chat/completions"
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []
    payload: dict[str, Any] = {
        "model": model,
        "messages": _openai_messages_from_list(messages=messages, merge_system_into_user=False),
        **filtered_params,
        "stream": True,
    }

    def _open_stream(payload_obj: dict[str, Any]) -> httpx._client.StreamContextManager[httpx.Response]:
        return client.stream(
            "POST",
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=payload_obj,
            timeout=timeout,
        )

    def drop_param(name: str) -> bool:
        if name not in payload:
            return False
        payload.pop(name, None)
        compat_dropped_params.append(name)
        compat_adjustments.append(f"drop_{name}")
        return True

    def clamp_max_tokens(limit: int) -> bool:
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

    def use_max_completion_tokens() -> bool:
        if provider != "openai":
            return False
        if "max_tokens" not in payload:
            return False
        if "max_completion_tokens" in payload:
            return False
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        compat_adjustments.append("use_max_completion_tokens")
        return True

    def merge_system_into_user() -> bool:
        payload["messages"] = _openai_messages_from_list(messages=messages, merge_system_into_user=True)
        compat_adjustments.append("merge_system_into_user")
        return True

    downgrade_steps: list[Callable[[], bool]] = [
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

                if provider in ("openai", "openai_compatible") and status_code in (400, 422) and attempts <= (len(downgrade_steps) + 1):
                    changed = False
                    for step in downgrade_steps:
                        if step():
                            changed = True
                            break
                    if changed:
                        continue

                extra_details = None
                if compat_adjustments:
                    extra_details = {
                        "compat_adjustments": compat_adjustments,
                        "compat_dropped_params": sorted(set(compat_dropped_params)),
                    }
                raise _map_upstream_error(status_code, _redact(upstream_text or ""), extra_details=extra_details)

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

                delta = _extract_openai_stream_delta_text(data)
                if delta:
                    yield delta

                finish_reason = _extract_openai_finish_reason(data)
                if finish_reason:
                    state.finish_reason = finish_reason
        except httpx.TimeoutException as exc:
            raise AppError(code="LLM_TIMEOUT", message="连接超时，请检查网络或 base_url 是否正确", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError(code="LLM_UPSTREAM_ERROR", message="连接失败，请检查网络或 base_url 是否正确", status_code=502) from exc
        finally:
            state.latency_ms = int((time.perf_counter() - start) * 1000)
            merged_dropped = dropped + [p for p in compat_dropped_params if p not in dropped]
            state.dropped_params = merged_dropped
            if cm is not None:
                cm.__exit__(None, None, None)

    return generator(), state


def call_llm(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    system: str,
    user: str,
    params: dict[str, Any],
    timeout_seconds: int,
    extra: dict[str, Any] | None = None,
) -> LLMCallResult:
    if not api_key:
        raise AppError(code="LLM_KEY_MISSING", message="缺少 API Key（请在 Prompts 页填写）", status_code=401)

    base_url = normalize_base_url(base_url)
    filtered_params, dropped = _filter_params(provider, params)
    extra = extra or {}

    start = time.perf_counter()
    try:
        client = get_llm_http_client()
        read_timeout = max(1.0, float(timeout_seconds))
        connect_timeout = min(10.0, read_timeout)
        write_timeout = min(10.0, read_timeout)
        pool_timeout = min(10.0, read_timeout)
        timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=write_timeout, pool=pool_timeout)

        if provider in ("openai", "openai_compatible"):
            endpoint = f"{base_url}/chat/completions"
            compat_dropped_params: list[str] = []
            compat_adjustments: list[str] = []
            payload: dict[str, Any] = {
                "model": model,
                "messages": _openai_messages(system=system, user=user, merge_system_into_user=False),
                **filtered_params,
            }

            def post_openai(payload_obj: dict[str, Any]) -> httpx.Response:
                return client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
                    json=payload_obj,
                    timeout=timeout,
                )

            resp = post_openai(payload)
            if provider in ("openai", "openai_compatible") and resp.status_code in (400, 422):
                # Some gateways/models reject otherwise-valid OpenAI params or roles.
                # Apply a short, deterministic downgrade sequence.
                def drop_param(name: str) -> bool:
                    if name not in payload:
                        return False
                    payload.pop(name, None)
                    compat_dropped_params.append(name)
                    compat_adjustments.append(f"drop_{name}")
                    return True

                def clamp_max_tokens(limit: int) -> bool:
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

                def use_max_completion_tokens() -> bool:
                    if provider != "openai":
                        return False
                    if "max_tokens" not in payload:
                        return False
                    if "max_completion_tokens" in payload:
                        return False
                    payload["max_completion_tokens"] = payload.pop("max_tokens")
                    compat_adjustments.append("use_max_completion_tokens")
                    return True

                def merge_system_into_user() -> bool:
                    if not system.strip():
                        return False
                    payload["messages"] = _openai_messages(system=system, user=user, merge_system_into_user=True)
                    compat_adjustments.append("merge_system_into_user")
                    return True

                downgrade_steps: list[Callable[[], bool]] = [
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

                for apply in downgrade_steps:
                    if resp.status_code not in (400, 422):
                        break
                    changed = apply()
                    if not changed:
                        continue
                    resp = post_openai(payload)

            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code // 100 != 2:
                extra_details = None
                if compat_adjustments:
                    extra_details = {
                        "compat_adjustments": compat_adjustments,
                        "compat_dropped_params": sorted(set(compat_dropped_params)),
                    }
                raise _map_upstream_error(resp.status_code, _redact(resp.text), extra_details=extra_details)
            data = resp.json()
            text = _extract_openai_like_text(data)
            finish_reason = _extract_openai_finish_reason(data)
            if text is None:
                details: dict[str, Any] = {}
                if settings.app_env == "dev":
                    details["upstream_response"] = _redact(resp.text)[:500]
                raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应格式不兼容，无法解析输出文本", status_code=502, details=details)
            merged_dropped = dropped + [p for p in compat_dropped_params if p not in dropped]
            return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=merged_dropped, finish_reason=finish_reason)

        if provider == "anthropic":
            endpoint = f"{base_url}/v1/messages"
            anthropic_version = extra.get("anthropic_version") or extra.get("anthropicVersion") or "2023-06-01"
            max_tokens = int(filtered_params.get("max_tokens") or 1500)
            system_prompt = system if system.strip() else None
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": filtered_params.get("temperature"),
                "top_p": filtered_params.get("top_p"),
                "top_k": filtered_params.get("top_k"),
                "stop_sequences": filtered_params.get("stop"),
                "system": system_prompt,
                "messages": [{"role": "user", "content": user}],
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
                limit = _extract_max_tokens_upper_bound(_redact(resp.text))
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
                raise _map_upstream_error(resp.status_code, _redact(resp.text), extra_details=extra_details)
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
                dropped_params=dropped,
                finish_reason=str(finish_reason) if isinstance(finish_reason, str) else None,
            )

        if provider == "gemini":
            endpoint = f"{base_url}/v1beta/models/{model}:generateContent"
            url = f"{endpoint}?{urlencode({'key': api_key})}"
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

            payload: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": generation_config}
            if system.strip():
                payload["systemInstruction"] = {"parts": [{"text": system}]}
            safety = extra.get("safety_settings") or extra.get("safetySettings")
            if safety is not None:
                payload["safetySettings"] = safety

            resp = client.post(
                url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
                timeout=timeout,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code // 100 != 2:
                raise _map_upstream_error(resp.status_code, _redact(resp.text))
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return LLMCallResult(text="", latency_ms=latency_ms, dropped_params=dropped, finish_reason=None)
            finish_reason = candidates[0].get("finishReason") if isinstance(candidates[0], dict) else None
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
            text = "".join(text_parts)
            return LLMCallResult(
                text=text,
                latency_ms=latency_ms,
                dropped_params=dropped,
                finish_reason=str(finish_reason) if isinstance(finish_reason, str) else None,
            )

        raise AppError(code="LLM_CONFIG_ERROR", message="不支持的 provider", status_code=400)
    except httpx.TimeoutException as exc:
        raise AppError(code="LLM_TIMEOUT", message="连接超时，请检查网络或 base_url 是否正确", status_code=504) from exc
    except httpx.HTTPError as exc:
        raise AppError(code="LLM_UPSTREAM_ERROR", message="连接失败，请检查网络或 base_url 是否正确", status_code=502) from exc
    except json.JSONDecodeError as exc:
        raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应解析失败", status_code=502) from exc


def call_llm_messages(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    messages: list[ChatMessage],
    params: dict[str, Any],
    timeout_seconds: int,
    extra: dict[str, Any] | None = None,
) -> LLMCallResult:
    if not api_key:
        raise AppError(code="LLM_KEY_MISSING", message="缺少 API Key（请在 Prompts 页填写）", status_code=401)

    base_url = normalize_base_url(base_url)
    filtered_params, dropped = _filter_params(provider, params)
    extra = extra or {}

    start = time.perf_counter()
    try:
        client = get_llm_http_client()
        read_timeout = max(1.0, float(timeout_seconds))
        connect_timeout = min(10.0, read_timeout)
        write_timeout = min(10.0, read_timeout)
        pool_timeout = min(10.0, read_timeout)
        timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=write_timeout, pool=pool_timeout)

        if provider in ("openai", "openai_compatible"):
            endpoint = f"{base_url}/chat/completions"
            compat_dropped_params: list[str] = []
            compat_adjustments: list[str] = []
            payload: dict[str, Any] = {
                "model": model,
                "messages": _openai_messages_from_list(messages=messages, merge_system_into_user=False),
                **filtered_params,
            }

            def post_openai(payload_obj: dict[str, Any]) -> httpx.Response:
                return client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
                    json=payload_obj,
                    timeout=timeout,
                )

            resp = post_openai(payload)
            if provider in ("openai", "openai_compatible") and resp.status_code in (400, 422):
                # Some gateways/models reject otherwise-valid OpenAI params or roles.
                # Apply a short, deterministic downgrade sequence.
                def drop_param(name: str) -> bool:
                    if name not in payload:
                        return False
                    payload.pop(name, None)
                    compat_dropped_params.append(name)
                    compat_adjustments.append(f"drop_{name}")
                    return True

                def clamp_max_tokens(limit: int) -> bool:
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

                def use_max_completion_tokens() -> bool:
                    if provider != "openai":
                        return False
                    if "max_tokens" not in payload:
                        return False
                    if "max_completion_tokens" in payload:
                        return False
                    payload["max_completion_tokens"] = payload.pop("max_tokens")
                    compat_adjustments.append("use_max_completion_tokens")
                    return True

                def merge_system_into_user() -> bool:
                    payload["messages"] = _openai_messages_from_list(messages=messages, merge_system_into_user=True)
                    compat_adjustments.append("merge_system_into_user")
                    return True

                downgrade_steps: list[Callable[[], bool]] = [
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

                for apply in downgrade_steps:
                    if resp.status_code not in (400, 422):
                        break
                    changed = apply()
                    if not changed:
                        continue
                    resp = post_openai(payload)

            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code // 100 != 2:
                extra_details = None
                if compat_adjustments:
                    extra_details = {
                        "compat_adjustments": compat_adjustments,
                        "compat_dropped_params": sorted(set(compat_dropped_params)),
                    }
                raise _map_upstream_error(resp.status_code, _redact(resp.text), extra_details=extra_details)
            data = resp.json()
            text = _extract_openai_like_text(data)
            finish_reason = _extract_openai_finish_reason(data)
            if text is None:
                details: dict[str, Any] = {}
                if settings.app_env == "dev":
                    details["upstream_response"] = _redact(resp.text)[:500]
                raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应格式不兼容，无法解析输出文本", status_code=502, details=details)
            merged_dropped = dropped + [p for p in compat_dropped_params if p not in dropped]
            return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=merged_dropped, finish_reason=finish_reason)

        if provider == "anthropic":
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
                limit = _extract_max_tokens_upper_bound(_redact(resp.text))
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
                raise _map_upstream_error(resp.status_code, _redact(resp.text), extra_details=extra_details)
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
                dropped_params=dropped,
                finish_reason=str(finish_reason) if isinstance(finish_reason, str) else None,
            )

        if provider == "gemini":
            endpoint = f"{base_url}/v1beta/models/{model}:generateContent"
            url = f"{endpoint}?{urlencode({'key': api_key})}"
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
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
                timeout=timeout,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code // 100 != 2:
                raise _map_upstream_error(resp.status_code, _redact(resp.text))
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return LLMCallResult(text="", latency_ms=latency_ms, dropped_params=dropped, finish_reason=None)
            finish_reason = candidates[0].get("finishReason") if isinstance(candidates[0], dict) else None
            content_obj = candidates[0].get("content") or {}
            parts = content_obj.get("parts") or []
            text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
            text = "".join(text_parts)
            return LLMCallResult(
                text=text,
                latency_ms=latency_ms,
                dropped_params=dropped,
                finish_reason=str(finish_reason) if isinstance(finish_reason, str) else None,
            )

        raise AppError(code="LLM_CONFIG_ERROR", message="不支持的 provider", status_code=400)
    except httpx.TimeoutException as exc:
        raise AppError(code="LLM_TIMEOUT", message="连接超时，请检查网络或 base_url 是否正确", status_code=504) from exc
    except httpx.HTTPError as exc:
        raise AppError(code="LLM_UPSTREAM_ERROR", message="连接失败，请检查网络或 base_url 是否正确", status_code=502) from exc
    except json.JSONDecodeError as exc:
        raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应解析失败", status_code=502) from exc


_KEY_QS_RE = re.compile(r"(?i)(key=)[^&\\s\\\"]+")
_ANTHROPIC_KEY_RE = re.compile(r"(?i)sk-ant-[A-Za-z0-9_-]{8,}")
_OPENAI_KEY_RE = re.compile(r"(?i)sk-[A-Za-z0-9_-]{8,}")
_GOOGLE_KEY_RE = re.compile(r"\\bAIza[0-9A-Za-z_\\-]{10,}\\b")
_BEARER_TOKEN_RE = re.compile(r"(?i)(bearer\\s+)[A-Za-z0-9._\\-]{8,}")
_X_LLM_API_KEY_RE = re.compile(r"(?i)(x-llm-api-key\\s*[:=]\\s*)[^\\s\\\"']+")


def _redact(text: str) -> str:
    if not text:
        return text
    text = _KEY_QS_RE.sub(r"\\1***", text)
    text = _ANTHROPIC_KEY_RE.sub("sk-ant-***", text)
    text = _OPENAI_KEY_RE.sub("sk-***", text)
    text = _GOOGLE_KEY_RE.sub("AIza***", text)
    text = _BEARER_TOKEN_RE.sub(r"\\1***", text)
    text = _X_LLM_API_KEY_RE.sub(r"\\1***", text)
    return text
