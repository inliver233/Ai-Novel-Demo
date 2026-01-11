from __future__ import annotations

import json
from typing import Any, TypeVar

T = TypeVar("T")

# Large user-authored markdown/text (outline/chapter/worldbook/settings/etc).
MAX_MD_CHARS = 200_000

# Medium free-form text (plans/summaries/profiles/notes).
MAX_TEXT_CHARS = 40_000

# Prompt templates are user-editable but should still be bounded.
MAX_TEMPLATE_CHARS = 100_000

# Open-shape JSON blobs (dict/Any) should be bounded to avoid DoS.
MAX_JSON_CHARS_SMALL = 20_000
MAX_JSON_CHARS_MEDIUM = 100_000


def compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def validate_json_chars(value: T | None, *, max_chars: int, field_name: str) -> T | None:
    if value is None:
        return None
    raw = compact_json_dumps(value)
    if len(raw) > max_chars:
        raise ValueError(f"{field_name} too large ({len(raw)} chars)")
    return value
