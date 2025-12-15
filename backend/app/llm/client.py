from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from app.core.errors import AppError
from app.core.config import settings
from app.llm.http_client import get_llm_http_client
from app.llm.utils import normalize_base_url


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    text: str
    latency_ms: int
    dropped_params: list[str]


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
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload_obj,
                    timeout=timeout,
                )

            resp = post_openai(payload)
            if provider == "openai_compatible" and resp.status_code in (400, 422):
                # Some gateways reject otherwise-valid OpenAI params or roles.
                # Apply a short, deterministic downgrade sequence (no streaming).
                def drop_param(name: str) -> bool:
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
                    lambda: clamp_max_tokens(1024),
                    lambda: drop_param("max_tokens"),
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
            if text is None:
                details: dict[str, Any] = {}
                if settings.app_env == "dev":
                    details["upstream_response"] = _redact(resp.text)[:500]
                raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应格式不兼容，无法解析输出文本", status_code=502, details=details)
            merged_dropped = dropped + [p for p in compat_dropped_params if p not in dropped]
            return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=merged_dropped)

        if provider == "anthropic":
            endpoint = f"{base_url}/v1/messages"
            anthropic_version = extra.get("anthropic_version") or extra.get("anthropicVersion") or "2023-06-01"
            max_tokens = int(filtered_params.get("max_tokens") or 1500)
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": filtered_params.get("temperature"),
                "top_p": filtered_params.get("top_p"),
                "top_k": filtered_params.get("top_k"),
                "stop_sequences": filtered_params.get("stop"),
                "system": system,
                "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            resp = client.post(
                endpoint,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": str(anthropic_version),
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code // 100 != 2:
                raise _map_upstream_error(resp.status_code, _redact(resp.text))
            data = resp.json()
            parts = data.get("content") or []
            text_parts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            text = "".join(text_parts).strip()
            return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=dropped)

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

            payload: dict[str, Any] = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": generation_config,
            }
            safety = extra.get("safety_settings") or extra.get("safetySettings")
            if safety is not None:
                payload["safetySettings"] = safety

            resp = client.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code // 100 != 2:
                raise _map_upstream_error(resp.status_code, _redact(resp.text))
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return LLMCallResult(text="", latency_ms=latency_ms, dropped_params=dropped)
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text = ""
            if parts and isinstance(parts[0], dict):
                text = parts[0].get("text", "")
            return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=dropped)

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
