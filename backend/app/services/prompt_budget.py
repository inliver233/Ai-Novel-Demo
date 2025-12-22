from __future__ import annotations

import math


def estimate_tokens(text: str) -> int:
    """
    Heuristic token estimator (no tokenizer dependency).

    - CJK characters are roughly 1 token each.
    - Other characters are roughly 4 chars per token.
    """
    if not text:
        return 0
    cjk = 0
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF:
            cjk += 1
    other = max(0, len(text) - cjk)
    return cjk + int(math.ceil(other / 4.0))


def trim_text_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if not text:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    # Binary search by character length as an approximation.
    lo = 0
    hi = len(text)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid]
        tokens = estimate_tokens(candidate)
        if tokens <= max_tokens:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return text[:best]

