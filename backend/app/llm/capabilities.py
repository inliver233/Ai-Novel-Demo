from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelTokenCaps:
    max_output_tokens: int | None
    max_context_tokens: int | None


_OPENAI_PREFIX_CAPS: list[tuple[str, ModelTokenCaps]] = [
    ("gpt-4o-mini", ModelTokenCaps(max_output_tokens=16384, max_context_tokens=128000)),
    ("gpt-4o", ModelTokenCaps(max_output_tokens=16384, max_context_tokens=128000)),
    ("gpt-4", ModelTokenCaps(max_output_tokens=8192, max_context_tokens=8192)),
]


def _normalize_provider(provider: str) -> str:
    return (provider or "").strip()


def _normalize_model(model: str | None) -> str:
    return (model or "").strip()


def get_model_token_caps(provider: str, model: str | None) -> ModelTokenCaps | None:
    p = _normalize_provider(provider)
    m = _normalize_model(model)
    if not m:
        return None

    if p in ("openai", "openai_responses"):
        for prefix, caps in _OPENAI_PREFIX_CAPS:
            if m == prefix or m.startswith(prefix + "-"):
                return caps
        return None

    # openai_compatible gateways vary widely; do not guess.
    return None


def max_output_tokens_limit(provider: str, model: str | None) -> int | None:
    caps = get_model_token_caps(provider, model)
    return caps.max_output_tokens if caps else None


def max_context_tokens_limit(provider: str, model: str | None) -> int | None:
    caps = get_model_token_caps(provider, model)
    return caps.max_context_tokens if caps else None


def recommended_max_tokens(provider: str, model: str | None) -> int:
    p = _normalize_provider(provider)
    limit = max_output_tokens_limit(provider, model)
    if isinstance(limit, int) and limit > 0:
        return min(12000, limit)
    if p in ("openai", "openai_responses", "openai_compatible", "openai_responses_compatible"):
        return 12000
    if p in ("anthropic", "gemini"):
        return 8192
    return 8192
