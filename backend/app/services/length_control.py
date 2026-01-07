from __future__ import annotations


_PROVIDER_MAX_TOKENS: dict[str, int] = {
    "anthropic": 8192,
    "gemini": 8192,
    "openai": 8192,
    "openai_responses": 8192,
    "openai_compatible": 8192,
    "openai_responses_compatible": 8192,
}


def estimate_max_tokens(*, target_word_count: int, provider: str | None = None, model: str | None = None) -> int:
    from app.llm.capabilities import max_output_tokens_limit

    if target_word_count <= 0:
        return 1500
    cap = max_output_tokens_limit(provider or "", model) or _PROVIDER_MAX_TOKENS.get(provider or "", 8192)
    estimated = int(target_word_count * 1.4) + 512
    return max(256, min(cap, estimated))
