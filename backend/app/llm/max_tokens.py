from __future__ import annotations

import json
import re
from typing import Any

_MAX_TOKENS_UPPER_BOUND_RE_LIST = [
    re.compile(r"(?i)max(?:_tokens?|\s+tokens?)\s*>\s*(\d{3,})"),
    re.compile(r"(?i)max(?:_tokens?|\s+tokens?)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
    re.compile(r"(?i)max(?:_completion_tokens|\s+completion\s+tokens?)\s*>\s*(\d{3,})"),
    re.compile(r"(?i)max(?:_completion_tokens|\s+completion\s+tokens?)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
    re.compile(r"(?i)max(?:CompletionTokens)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
    re.compile(r"(?i)max(?:_output_tokens|\s+output\s+tokens?)\s*>\s*(\d{3,})"),
    re.compile(r"(?i)max(?:_output_tokens|\s+output\s+tokens?)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
    re.compile(r"(?i)max(?:OutputTokens|\s+output\s+tokens?)\s*(?:must\s*be\s*)?<=\s*(\d{3,})"),
]


def extract_max_tokens_upper_bound(text: str) -> int | None:
    if not text:
        return None
    candidates: list[str] = [text]
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    if parsed is not None:
        candidates = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                candidates.append(node)
                return
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
                return
            if isinstance(node, list):
                for value in node:
                    walk(value)
                return

        walk(parsed)
        candidates.append(text)

    for candidate in candidates:
        for pattern in _MAX_TOKENS_UPPER_BOUND_RE_LIST:
            match = pattern.search(candidate)
            if not match:
                continue
            try:
                value = int(match.group(1))
            except Exception:
                continue
            if value > 0:
                return value
    return None
