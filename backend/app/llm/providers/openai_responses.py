from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.llm.messages import coalesce_system, flatten_messages, merge_consecutive
from app.llm.max_tokens import extract_max_tokens_upper_bound
from app.llm.openai_extract import extract_openai_like_text
from app.llm.openai_messages import openai_messages_from_list
from app.llm.redaction import redact_text
from app.llm.types import LLMCallResult, LLMStreamState
from app.llm.upstream_errors import map_upstream_error


def _looks_like_stream_required_error(upstream_text: str | None) -> bool:
    if not upstream_text:
        return False
    normalized = upstream_text.lower()
    return "stream must be set to true" in normalized


def _looks_like_input_list_required_error(upstream_text: str | None) -> bool:
    if not upstream_text:
        return False
    normalized = upstream_text.lower()
    return "input must be a list" in normalized


def _candidate_responses_endpoints(base_url: str) -> list[str]:
    normalized = (base_url or "").strip().rstrip("/")
    endpoints = [f"{normalized}/responses"]
    if not normalized.endswith("/v1"):
        endpoints.append(f"{normalized}/v1/responses")
    return endpoints


def _responses_input_from_messages(*, messages: list, merge_system_into_user: bool) -> list[dict[str, Any]]:
    # Convert to Responses message content blocks.
    #
    # IMPORTANT: Many OpenAI-compatible gateways are picky about "system" role. We already send system content via
    # `instructions`, so build message items from non-system messages only.
    normalized = merge_consecutive(messages)
    _, non_system = coalesce_system(normalized)
    openai_messages = openai_messages_from_list(messages=non_system, merge_system_into_user=merge_system_into_user)
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
        payload: dict[str, Any] = {"type": "message", "role": role, "content": [{"type": block_type, "text": content}]}
        name = msg.get("name")
        if isinstance(name, str) and name.strip():
            payload["name"] = name.strip()
        out.append(payload)
    if not out:
        out = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": ""}]}]
    return out


def _responses_input_text_from_messages(*, messages: list) -> tuple[str | None, str]:
    normalized = merge_consecutive(messages)
    system, non_system = coalesce_system(normalized)
    instructions = system.strip() or None
    input_text = flatten_messages(non_system).strip()
    return instructions, input_text


def _coerce_text_config(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None

    verbosity = extra.get("text_verbosity") or extra.get("textVerbosity") or extra.get("verbosity")
    verbosity_value = verbosity.strip() if isinstance(verbosity, str) and verbosity.strip() else None

    text = extra.get("text")
    if isinstance(text, dict):
        out = dict(text)
        if verbosity_value and not isinstance(out.get("verbosity"), str):
            out["verbosity"] = verbosity_value
        return out

    text_format = extra.get("text_format") or extra.get("textFormat")
    if isinstance(text_format, dict):
        out: dict[str, Any] = {"format": text_format}
        if verbosity_value:
            out["verbosity"] = verbosity_value
        return out

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
            out = {"format": fmt}
            if verbosity_value:
                out["verbosity"] = verbosity_value
            return out
        out = {"format": response_format}
        if verbosity_value:
            out["verbosity"] = verbosity_value
        return out

    if verbosity_value:
        return {"verbosity": verbosity_value}

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
    for key in ("max_output_tokens", "max_tokens"):
        current = payload.get(key)
        if not isinstance(current, int):
            continue
        if current <= limit:
            continue
        payload[key] = limit
        compat_adjustments.append(f"clamp_{key}_{limit}")
        return True
    return False


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

    def merge_instructions_into_input() -> bool:
        if "instructions" not in payload:
            return False
        instructions = payload.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            payload.pop("instructions", None)
            compat_dropped_params.append("instructions")
            compat_adjustments.append("drop_instructions")
            return True
        input_value = payload.get("input")
        if isinstance(input_value, str):
            payload["input"] = f"{instructions}\n\n{input_value}" if input_value.strip() else instructions
        elif isinstance(input_value, list):
            merged = False
            for item in input_value:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                if role != "user":
                    continue
                content = item.get("content")
                if isinstance(content, str):
                    item["content"] = f"{instructions}\n\n{content}" if content.strip() else instructions
                    merged = True
                    break
                if isinstance(content, list) and content:
                    first = content[0]
                    if isinstance(first, dict) and isinstance(first.get("text"), str):
                        existing = first.get("text") or ""
                        first["text"] = f"{instructions}\n\n{existing}" if str(existing).strip() else instructions
                        merged = True
                        break
            if not merged:
                input_value.insert(
                    0,
                    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": instructions}]},
                )
                merged = True
            payload["input"] = input_value
        else:
            return False
        payload.pop("instructions", None)
        compat_dropped_params.append("instructions")
        compat_adjustments.append("merge_instructions_into_input")
        return True

    def switch_to_message_input() -> bool:
        if not isinstance(payload.get("input"), str):
            return False
        instructions, _ = _responses_input_text_from_messages(messages=messages)
        if instructions:
            payload["instructions"] = instructions
            compat_adjustments.append("restore_instructions")
        payload["input"] = _responses_input_from_messages(messages=messages, merge_system_into_user=False)
        compat_adjustments.append("switch_input_to_messages")
        return True

    def use_max_tokens_param() -> bool:
        # Some OpenAI-compatible gateways implement `/responses` but only accept `max_tokens`.
        if not provider.endswith("_compatible"):
            return False
        if "max_output_tokens" not in payload:
            return False
        if "max_tokens" in payload:
            return False
        payload["max_tokens"] = payload.pop("max_output_tokens")
        compat_adjustments.append("use_max_tokens_param")
        return True

    def clamp_max_tokens(limit: int) -> bool:
        return _clamp_payload_max_output_tokens(payload, limit=limit, compat_adjustments=compat_adjustments)

    return [
        switch_to_message_input,
        lambda: drop_param("stop"),
        lambda: drop_param("top_p"),
        lambda: drop_param("temperature"),
        lambda: drop_param("presence_penalty"),
        lambda: drop_param("frequency_penalty"),
        lambda: drop_param("seed"),
        lambda: drop_param("reasoning"),
        drop_text_format,
        merge_instructions_into_input,
        lambda: clamp_max_tokens(16384),
        lambda: clamp_max_tokens(8192),
        lambda: clamp_max_tokens(4096),
        lambda: clamp_max_tokens(1024),
        use_max_tokens_param,
        lambda: drop_param("max_output_tokens"),
        lambda: drop_param("max_tokens"),
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
    endpoints = _candidate_responses_endpoints(base_url)
    endpoint_idx = 0
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []

    instructions, input_text = _responses_input_text_from_messages(messages=messages)
    payload: dict[str, Any] = {
        "model": model,
        "input": input_text,
        "instructions": instructions,
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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if provider.endswith("_compatible"):
            headers["x-api-key"] = api_key
        return client.post(
            endpoints[endpoint_idx],
            headers=headers,
            json=payload_obj,
            timeout=timeout,
        )

    resp = post_openai(payload)
    if endpoint_idx == 0 and len(endpoints) > 1 and (
        resp.status_code == 404 or (provider.endswith("_compatible") and resp.status_code in (400, 405, 422))
    ):
        endpoint_idx = 1
        compat_adjustments.append("append_v1_base_url")
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
            if _looks_like_stream_required_error(resp.text):
                break
            changed = apply()
            if not changed:
                continue
            resp = post_openai(payload)

    latency_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code // 100 != 2:
        if resp.status_code in (400, 404, 405, 422) and (
            _looks_like_stream_required_error(resp.text) or _looks_like_input_list_required_error(resp.text)
        ):
            stream_iter, stream_state = call_openai_responses_stream(
                client=client,
                provider=provider,
                base_url=base_url,
                model=model,
                api_key=api_key,
                messages=messages,
                filtered_params=filtered_params,
                dropped_params=dropped_params,
                timeout=timeout,
                start=start,
                extra=extra,
            )
            text = "".join(list(stream_iter))
            stream_latency = stream_state.latency_ms if stream_state.latency_ms is not None else latency_ms
            return LLMCallResult(
                text=text,
                latency_ms=stream_latency,
                dropped_params=stream_state.dropped_params,
                finish_reason=stream_state.finish_reason,
            )

        if provider.endswith("_compatible") and resp.status_code in (400, 404, 405, 422):
            from app.llm.providers.openai_chat import call_openai_chat_completions

            merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
            fallback_extra = dict(extra or {})
            fallback_extra["_internal_from_responses_fallback"] = True
            return call_openai_chat_completions(
                client=client,
                provider="openai_compatible",
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
    endpoints = _candidate_responses_endpoints(base_url)
    endpoint_idx = 0
    state = LLMStreamState(dropped_params=dropped_params)
    compat_dropped_params: list[str] = []
    compat_adjustments: list[str] = []

    instructions, input_text = _responses_input_text_from_messages(messages=messages)
    payload: dict[str, Any] = {
        "model": model,
        "input": input_text,
        "instructions": instructions,
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

    downgrade_steps = _build_openai_responses_compat_steps(
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
        used_chat_fallback = False
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

                if endpoint_idx == 0 and len(endpoints) > 1 and (
                    status_code == 404 or (provider.endswith("_compatible") and status_code in (400, 405, 422))
                ):
                    endpoint_idx = 1
                    compat_adjustments.append("append_v1_base_url")
                    continue

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

                if provider.endswith("_compatible") and status_code in (400, 404, 405, 422):
                    from app.llm.providers.openai_chat import call_openai_chat_completions_stream

                    used_chat_fallback = True
                    merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
                    fallback_extra = dict(extra or {})
                    fallback_extra["_internal_from_responses_fallback"] = True
                    fallback_iter, fallback_state = call_openai_chat_completions_stream(
                        client=client,
                        provider="openai_compatible",
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
            if not used_chat_fallback:
                state.latency_ms = int((time.perf_counter() - start) * 1000)
                merged_dropped = dropped_params + [p for p in compat_dropped_params if p not in dropped_params]
                state.dropped_params = merged_dropped
            if cm is not None:
                cm.__exit__(None, None, None)

    return generator(), state
