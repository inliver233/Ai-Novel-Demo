from __future__ import annotations

import re


def _split_paragraphs(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"\n\s*\n", raw)
    return [p.strip() for p in parts if p.strip()]


def _validate_rewrite_output(*, raw_content: str, edited_content: str, prefix: str) -> list[str]:
    """
    Returns warning codes; empty list means output is acceptable.
    """
    prefix_norm = (prefix or "").strip() or "rewrite"
    raw = (raw_content or "").strip()
    edited = (edited_content or "").strip()
    if not edited:
        return [f"{prefix_norm}_no_content"]

    raw_len = len(raw)
    edited_len = len(edited)
    if edited_len < 80:
        return [f"{prefix_norm}_too_short"]
    if raw_len >= 400 and edited_len < int(raw_len * 0.4):
        return [f"{prefix_norm}_too_short"]

    raw_paras = _split_paragraphs(raw)
    edited_paras = _split_paragraphs(edited)
    if len(raw_paras) >= 4 and len(edited_paras) < max(2, int(len(raw_paras) * 0.5)):
        return [f"{prefix_norm}_missing_paragraphs"]

    return []


def validate_post_edit_output(*, raw_content: str, edited_content: str) -> list[str]:
    return _validate_rewrite_output(raw_content=raw_content, edited_content=edited_content, prefix="post_edit")


def validate_content_optimize_output(*, raw_content: str, optimized_content: str) -> list[str]:
    return _validate_rewrite_output(raw_content=raw_content, edited_content=optimized_content, prefix="content_optimize")
