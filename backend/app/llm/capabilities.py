from __future__ import annotations

from dataclasses import dataclass

from app.llm.registry import (
    max_context_tokens_limit as registry_max_context_tokens_limit,
    max_output_tokens_limit as registry_max_output_tokens_limit,
    recommended_max_tokens as registry_recommended_max_tokens,
)


@dataclass(frozen=True, slots=True)
class ModelTokenCaps:
    max_output_tokens: int | None
    max_context_tokens: int | None


def get_model_token_caps(provider: str, model: str | None) -> ModelTokenCaps | None:
    max_output = registry_max_output_tokens_limit(provider, model, mode="audit")
    max_context = registry_max_context_tokens_limit(provider, model, mode="audit")
    if max_output is None and max_context is None:
        return None
    return ModelTokenCaps(max_output_tokens=max_output, max_context_tokens=max_context)


def max_output_tokens_limit(provider: str, model: str | None) -> int | None:
    return registry_max_output_tokens_limit(provider, model, mode="audit")


def max_context_tokens_limit(provider: str, model: str | None) -> int | None:
    return registry_max_context_tokens_limit(provider, model, mode="audit")


def recommended_max_tokens(provider: str, model: str | None) -> int:
    try:
        return registry_recommended_max_tokens(provider, model, mode="audit")
    except Exception:
        return 8192
