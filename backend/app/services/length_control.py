from __future__ import annotations


_PROVIDER_MAX_TOKENS: dict[str, int] = {
    "openai": 32000,
    "openai_compatible": 32000,
    "anthropic": 8192,
    "gemini": 8192,
}


def estimate_max_tokens(*, target_word_count: int, provider: str | None = None) -> int:
    if target_word_count <= 0:
        return 1500
    cap = _PROVIDER_MAX_TOKENS.get(provider or "", 8192)
    estimated = int(target_word_count * 1.4) + 512
    return max(256, min(cap, estimated))
