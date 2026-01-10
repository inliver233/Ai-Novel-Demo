from __future__ import annotations

import re


def _split_paragraphs(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"\n\s*\n", raw)
    return [p.strip() for p in parts if p.strip()]


def validate_post_edit_output(*, raw_content: str, edited_content: str) -> list[str]:
    """
    Returns warning codes; empty list means output is acceptable.
    """
    raw = (raw_content or "").strip()
    edited = (edited_content or "").strip()
    if not edited:
        return ["post_edit_no_content"]

    raw_len = len(raw)
    edited_len = len(edited)
    if edited_len < 80:
        return ["post_edit_too_short"]
    if raw_len >= 400 and edited_len < int(raw_len * 0.4):
        return ["post_edit_too_short"]

    raw_paras = _split_paragraphs(raw)
    edited_paras = _split_paragraphs(edited)
    if len(raw_paras) >= 4 and len(edited_paras) < max(2, int(len(raw_paras) * 0.5)):
        return ["post_edit_missing_paragraphs"]

    return []
