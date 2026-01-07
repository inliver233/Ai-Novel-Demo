from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.llm.max_tokens import extract_max_tokens_upper_bound
from app.llm.openai_extract import extract_openai_like_text
from app.llm.openai_messages import openai_messages_from_list
from app.llm.redaction import redact_text
from app.llm.types import LLMCallResult, LLMStreamState
from app.llm.upstream_errors import map_upstream_error


def _responses_input_from_messages(*, messages: list, merge_system_into_user: bool) -> list[dict[str, Any]]:
    # Start from the existing OpenAI ChatCompletions shape, then convert to Responses message content blocks.
    openai_messages = openai_messages_from_list(messages=messages, merge_system_into_user=merge_system_into_user)
    out: list[dict[str, Any]] = []
    for msg in openai_messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if not isinstance(role, str) or not role:
            continue
        content = msg.get("content")
        if not isinstance(content, str):
            content = "" if content is None else str(content)
        block_type = "output_text" if role == "assistant" else "input_text"
        payload: dict[str, Any] = {"role": role, "content": [{"type": block_type, "text": content}]}
        name = msg.get("name")
        if isinstance(name, str) and name.strip():
            payload["name"] = name.strip()
        out.append(payload)
    if not out:
        out = [{"role": "user", "content": [{"type": "input_text", "text": ""}]}]
    return out


def _coerce_text_config(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None

    text = extra.get("text")
    if isinstance(text, dict):
        return text

    text_format = extra.get("text_format") or extra.get("textFormat")
    if isinstance(text_format, dict):
        return {"format": text_format}

    # Convenience: accept Chat Completions `response_format` and convert common json_schema form.
    response_format = extra.get("response_format") or extra.get("responseFormat")
    if isinstance(response_format, dict):
        rf_type = response_format.get("type")
        if rf_type == "json_schema" and isinstance(response_format.get("json_schema"), dict):
            js = response_format["json_schema"]
            fmt: dict[str, Any] = {
                "type": "json_schema",
                "name": js.get("name") or "response",
                "schema": js.get("schema") or {},
                "strict": js.get("strict"),
            }
            fmt = {k: v for k, v in fmt.items() if v is not None}
            return {"format": fmt}
        return {"format": response_format}

    return None


def _coerce_reasoning_config(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None
    reasoning = extra.get("reasoning")
    if isinstance(reasoning, dict):
        return reasoning
    effort = extra.get("reasoning_effort") or extra.get("reasoningEffort")
    if isinstance(effort, str) and effort.strip():
        return {"effort": effort.strip()}
    return None


def _clamp_payload_max_output_tokens(payload: dict[str, Any], *, limit: int, compat_adjustments: list[str]) -> bool:
    current = payload.get("max_output_tokens")
    if not isinstance(current, int):
        return False
    if current <= limit:
        return False
    payload["max_output_tokens"] = limit
    compat_adjustments.append(f"clamp_max_output_tokens_{limit}")
    return True


def _build_openai_responses_compat_steps(
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

    def drop_text_format() -> bool:
        if "text" not in payload:
            return False
        payload.pop("text", None)
        compat_dropped_params.append("text")
        compat_adjustments.append("drop_text")
        return True

    def merge_system_into_user() -> bool:
        payload["input"] = _responses_input_from_messages(messages=messages, merge_system_into_user=True)
        compat_adjustments.append("merge_system_into_user")
        return True

    def clamp_max_tokens(limit: int) -> bool:
        return _clamp_payload_max_output_tokens(payload, limit=limit, compat_adjustments=compat_adjustments)

    return [
        lambda: drop_param("stop"),
        lambda: drop_param("top_p"),
        lambda: drop_param("temperature"),
        lambda: drop_param("presence_penalty"),
        lambda: drop_param("frequency_penalty"),
        lambda: drop_param("seed"),
        lambda: drop_param("reasoning"),
        drop_text_format,
        lambda: clamp_max_tokens(16384),
        lambda: clamp_max_tokens(8192),
        lambda: clamp_max_tokens(4096),
        lambda: clamp_max_tokens(1024),
        lambda: drop_param("max_output_tokens"),
        merge_system_into_user,
    ]


def call_openai_responses(
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
    endpoint = f"{base_url}/responses"
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []

    payload: dict[str, Any] = {
        "model": model,
        "input": _responses_input_from_messages(messages=messages, merge_system_into_user=False),
        "max_output_tokens": filtered_params.get("max_tokens"),
        "temperature": filtered_params.get("temperature"),
        "top_p": filtered_params.get("top_p"),
        "stop": filtered_params.get("stop"),
        "presence_penalty": filtered_params.get("presence_penalty"),
        "frequency_penalty": filtered_params.get("frequency_penalty"),
    }

    if extra:
        seed = extra.get("seed")
        if isinstance(seed, int):
            payload["seed"] = seed
        reasoning = _coerce_reasoning_config(extra)
        if reasoning is not None:
            payload["reasoning"] = reasoning
        text_cfg = _coerce_text_config(extra)
        if text_cfg is not None:
            payload["text"] = text_cfg

    payload = {k: v for k, v in payload.items() if v is not None}

    def post_openai(payload_obj: dict[str, Any]) -> httpx.Response:
        return client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload_obj,
            timeout=timeout,
        )

    resp = post_openai(payload)
    if provider in ("openai_responses", "openai_responses_compatible") and resp.status_code in (400, 422):
        upper = extract_max_tokens_upper_bound(redact_text(resp.text))
        if upper is not None and _clamp_payload_max_output_tokens(payload, limit=upper, compat_adjustments=compat_adjustments):
            resp = post_openai(payload)

        downgrade_steps = _build_openai_responses_compat_steps(
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
        extra_details = None
        if compat_adjustments:
            extra_details = {
                "compat_adjustments": compat_adjustments,
                "compat_dropped_params": sorted(set(compat_dropped_params)),
            }
        raise map_upstream_error(resp.status_code, redact_text(resp.text), extra_details=extra_details)

    data = resp.json()
    text = extract_openai_like_text(data)
    finish_reason = None
    if isinstance(data, dict) and isinstance(data.get("status"), str):
        finish_reason = data.get("status") or None
    if text is None:
        details: dict[str, Any] = {}
        if settings.app_env == "dev":
            details["upstream_response"] = redact_text(resp.text)[:500]
        raise AppError(code="LLM_UPSTREAM_ERROR", message="上游响应格式不兼容，无法解析输出文本", status_code=502, details=details)

    merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
    return LLMCallResult(text=text, latency_ms=latency_ms, dropped_params=merged_dropped, finish_reason=finish_reason)


def call_openai_responses_stream(
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
    endpoint = f"{base_url}/responses"
    state = LLMStreamState(dropped_params=dropped_params)
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []

    payload: dict[str, Any] = {
        "model": model,
        "input": _responses_input_from_messages(messages=messages, merge_system_into_user=False),
        "max_output_tokens": filtered_params.get("max_tokens"),
        "temperature": filtered_params.get("temperature"),
        "top_p": filtered_params.get("top_p"),
        "stop": filtered_params.get("stop"),
        "presence_penalty": filtered_params.get("presence_penalty"),
        "frequency_penalty": filtered_params.get("frequency_penalty"),
        "stream": True,
    }
    if extra:
        seed = extra.get("seed")
        if isinstance(seed, int):
            payload["seed"] = seed
        reasoning = _coerce_reasoning_config(extra)
        if reasoning is not None:
            payload["reasoning"] = reasoning
        text_cfg = _coerce_text_config(extra)
        if text_cfg is not None:
            payload["text"] = text_cfg
    payload = {k: v for k, v in payload.items() if v is not None}

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

    downgrade_steps = _build_openai_responses_compat_steps(
        provider=provider,
        payload=payload,
        messages=messages,
        compat_dropped_params=compat_dropped_params,
        compat_adjustments=compat_adjustments,
    )

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

                if provider in ("openai_responses", "openai_responses_compatible") and status_code in (400, 422) and attempts <= (
                    len(downgrade_steps) + 1
                ):
                    upper = extract_max_tokens_upper_bound(redact_text(upstream_text or ""))
                    if upper is not None and _clamp_payload_max_output_tokens(payload, limit=upper, compat_adjustments=compat_adjustments):
                        continue

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

                event_type = None
                if isinstance(data, dict) and isinstance(data.get("type"), str):
                    event_type = data["type"]
                if not event_type:
                    event_type = current_event or ""

                if event_type == "response.output_text.delta" and isinstance(data, dict) and isinstance(data.get("delta"), str):
                    yield data["delta"]
                    continue

                if event_type == "response.completed" and isinstance(data, dict):
                    resp_obj = data.get("response")
                    if isinstance(resp_obj, dict) and isinstance(resp_obj.get("status"), str):
                        state.finish_reason = resp_obj.get("status") or "completed"
                    else:
                        state.finish_reason = "completed"
                    break

                if event_type == "response.failed":
                    state.finish_reason = "failed"
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

