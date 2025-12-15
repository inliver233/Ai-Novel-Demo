from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError
from app.core.logging import log_event
from app.llm.client import call_llm
from app.models.llm_preset import LLMPreset
from app.services.run_store import write_generation_run


@dataclass(frozen=True, slots=True)
class PreparedLlmCall:
    provider: str
    model: str
    base_url: str
    timeout_seconds: int
    params: dict[str, Any]
    params_json: str
    extra: dict[str, Any]


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item is not None]


def _parse_json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def prepare_llm_call(preset: LLMPreset) -> PreparedLlmCall:
    stop = _parse_json_list(preset.stop_json)
    extra = _parse_json_dict(preset.extra_json)

    params: dict[str, Any] = {
        "temperature": preset.temperature,
        "top_p": preset.top_p,
        "max_tokens": preset.max_tokens,
        "presence_penalty": preset.presence_penalty,
        "frequency_penalty": preset.frequency_penalty,
        "top_k": preset.top_k,
        "stop": stop,
    }
    params_json = json.dumps(params, ensure_ascii=False)

    return PreparedLlmCall(
        provider=preset.provider,
        model=preset.model,
        base_url=preset.base_url or "",
        timeout_seconds=int(preset.timeout_seconds or 90),
        params=params,
        params_json=params_json,
        extra=extra,
    )


def call_llm_and_record(
    *,
    logger: logging.Logger,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    run_type: str,
    api_key: str,
    prompt_system: str,
    prompt_user: str,
    llm_call: PreparedLlmCall,
) -> str:
    try:
        result = call_llm(
            provider=llm_call.provider,
            base_url=llm_call.base_url,
            model=llm_call.model,
            api_key=api_key,
            system=prompt_system,
            user=prompt_user,
            params=llm_call.params,
            timeout_seconds=llm_call.timeout_seconds,
            extra=llm_call.extra,
        )
        raw_output = result.text

        log_event(
            logger,
            "info",
            llm={
                "provider": llm_call.provider,
                "model": llm_call.model,
                "timeout_seconds": llm_call.timeout_seconds,
                "prompt_chars": len(prompt_system) + len(prompt_user),
                "output_chars": len(raw_output or ""),
                "dropped_params": result.dropped_params,
            },
        )

        write_generation_run(
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            chapter_id=chapter_id,
            run_type=run_type,
            provider=llm_call.provider,
            model=llm_call.model,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            params_json=llm_call.params_json,
            output_text=raw_output,
            error_json=None,
        )

        return raw_output
    except AppError as exc:
        log_event(
            logger,
            "error",
            llm={
                "provider": llm_call.provider,
                "model": llm_call.model,
                "timeout_seconds": llm_call.timeout_seconds,
                "prompt_chars": len(prompt_system) + len(prompt_user),
                "output_chars": 0,
                "error_code": exc.code,
            },
        )
        write_generation_run(
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            chapter_id=chapter_id,
            run_type=run_type,
            provider=llm_call.provider,
            model=llm_call.model,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            params_json=llm_call.params_json,
            output_text=None,
            error_json=json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False),
        )
        raise

