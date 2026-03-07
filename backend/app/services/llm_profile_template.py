from __future__ import annotations

import json
from typing import Any

from app.models.llm_profile import LLMProfile
from app.services.llm_contract_service import (
    contract_metadata,
    normalize_base_url_for_provider,
    normalize_max_tokens_for_provider,
    normalize_provider_model,
)

DEFAULT_TIMEOUT_SECONDS = 180


def decode_stop_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            out: list[str] = []
            for item in parsed:
                if isinstance(item, str):
                    norm = item.strip()
                    if norm:
                        out.append(norm)
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


def llm_contract_meta(provider: str, model: str) -> dict[str, Any]:
    return contract_metadata(provider, model)


def apply_profile_template_to_llm_row(*, row: Any, profile: LLMProfile) -> None:
    provider, model = normalize_provider_model(str(profile.provider or "").strip(), str(profile.model or "").strip())
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
