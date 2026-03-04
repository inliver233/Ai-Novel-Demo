from __future__ import annotations

import json
from typing import Any

from app.core.errors import AppError
from app.llm.capabilities import max_output_tokens_limit
from app.llm.utils import default_max_tokens, normalize_base_url
from app.models.llm_profile import LLMProfile

DEFAULT_TIMEOUT_SECONDS = 180


def normalize_base_url_for_provider(provider: str, base_url: str | None) -> str | None:
    if provider in ("openai", "openai_responses"):
        return normalize_base_url(base_url or "https://api.openai.com/v1")
    if provider in ("openai_compatible", "openai_responses_compatible"):
        if not base_url:
            raise AppError(code="LLM_CONFIG_ERROR", message=f"{provider} 必须填写 base_url", status_code=400)
        return normalize_base_url(base_url)
    if provider == "anthropic":
        return normalize_base_url(base_url or "https://api.anthropic.com")
    if provider == "gemini":
        return normalize_base_url(base_url or "https://generativelanguage.googleapis.com")
    raise AppError(code="LLM_CONFIG_ERROR", message="不支持的 provider", status_code=400, details={"provider": provider})


def normalize_max_tokens_for_provider(provider: str, model: str, raw_value: int | None) -> int:
    if raw_value is None:
        return default_max_tokens(provider, model)
    max_tokens = int(raw_value)
    if max_tokens <= 0:
        raise AppError.validation(message="最大 tokens（max_tokens）必须为正整数")
    limit = max_output_tokens_limit(provider, model)
    return min(max_tokens, limit) if limit else max_tokens


def decode_stop_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            out: list[str] = []
            for item in parsed:
                if isinstance(item, str):
                    s = item.strip()
                    if s:
                        out.append(s)
            return out
        return []
    except Exception:
        return []


def decode_extra_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def encode_stop_json(stop: list[str] | None) -> str:
    return json.dumps(stop or [], ensure_ascii=False)


def encode_extra_json(extra: dict[str, Any] | None) -> str:
    return json.dumps(extra or {}, ensure_ascii=False)


def apply_profile_template_to_llm_row(*, row: Any, profile: LLMProfile) -> None:
    provider = str(profile.provider or "").strip()
    model = str(profile.model or "").strip()
    row.provider = provider
    row.base_url = normalize_base_url_for_provider(provider, profile.base_url)
    row.model = model
    row.temperature = profile.temperature
    row.top_p = profile.top_p
    row.max_tokens = normalize_max_tokens_for_provider(provider, model, profile.max_tokens)
    row.presence_penalty = profile.presence_penalty
    row.frequency_penalty = profile.frequency_penalty
    row.top_k = profile.top_k
    row.stop_json = encode_stop_json(decode_stop_json(profile.stop_json))
    row.timeout_seconds = int(profile.timeout_seconds or DEFAULT_TIMEOUT_SECONDS)
    row.extra_json = encode_extra_json(decode_extra_json(profile.extra_json))
