from __future__ import annotations

import json
from typing import Any

from app.services.output_parsers import parse_outline_output


def parse_outline_structure_json(value: str | None) -> Any | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def normalize_outline_content_and_structure(
    *, content_md: str | None, structure: Any | None
) -> tuple[str, Any | None, bool]:
    text = str(content_md or "")
    if structure is not None:
        return text, structure, False

    stripped = text.strip()
    if not stripped:
        return text, None, False

    data, _warnings, parse_error = parse_outline_output(stripped)
    chapters = data.get("chapters")
    if parse_error is not None or not isinstance(chapters, list) or len(chapters) == 0:
        return text, None, False

    outline_md = str(data.get("outline_md") or "").strip() or text
    return outline_md, {"chapters": chapters}, True
