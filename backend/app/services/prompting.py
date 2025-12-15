from __future__ import annotations

import json
import re
from typing import Any


_PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def render_template(template: str, values: dict[str, str]) -> tuple[str, list[str]]:
    missing: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return ""
        return values[key]

    return _PLACEHOLDER_RE.sub(_replace, template), sorted(missing)


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    candidate = m.group(1) if m else None
    if not candidate:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]

    if not candidate:
        return None, None

    try:
        return json.loads(candidate), candidate
    except Exception:
        return None, candidate
