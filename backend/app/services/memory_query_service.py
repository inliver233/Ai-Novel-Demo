from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.settings import QueryPreprocessingConfig


_TAG_PATTERN = re.compile(r"(^|\s)#([0-9A-Za-z_\-\u4e00-\u9fff]{1,64})")
_CHAPTER_REF_PATTERN = re.compile(r"第(\d{1,4})章")
_CHAPTER_REF_EN_PATTERN = re.compile(r"\bchapter\s*(\d{1,4})\b", flags=re.IGNORECASE)


def parse_query_preprocessing_config(raw_json: str | None) -> QueryPreprocessingConfig | None:
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    try:
        return QueryPreprocessingConfig.model_validate(data)
    except ValueError:
        return None


def normalize_query_text(
    *,
    query_text: str,
    config: QueryPreprocessingConfig | None,
) -> tuple[str, dict[str, Any]]:
    raw = query_text if isinstance(query_text, str) else str(query_text or "")
    enabled = bool(config and config.enabled)

    obs: dict[str, Any] = {
        "enabled": enabled,
        "raw_query_text": raw,
        "normalized_query_text": raw,
        "extracted_tags": [],
        "ignored_tags": [],
        "applied_exclusion_rules": [],
        "index_refs": [],
        "steps": [],
    }

    if not enabled:
        obs["steps"].append("disabled_passthrough")
        return raw, obs

    allow_tags = set(config.tags or []) if config and config.tags else None
    extracted_tags: list[str] = []
    ignored_tags: list[str] = []

    def _tag_repl(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        tag = match.group(2) or ""
        if allow_tags is None or tag in allow_tags:
            extracted_tags.append(tag)
            return prefix
        ignored_tags.append(tag)
        return match.group(0)

    text = _TAG_PATTERN.sub(_tag_repl, raw)
    obs["steps"].append("tag_extract")
    obs["extracted_tags"] = sorted(set(extracted_tags))
    obs["ignored_tags"] = sorted(set(ignored_tags))

    applied_rules: list[str] = []
    for rule in (config.exclusion_rules or []):
        if rule and rule in text:
            applied_rules.append(rule)
            text = text.replace(rule, " ")
    obs["steps"].append("exclusion_rules")
    obs["applied_exclusion_rules"] = applied_rules

    index_refs: list[str] = []
    if config.index_ref_enhance:
        nums: set[str] = set()
        for m in _CHAPTER_REF_PATTERN.finditer(text):
            nums.add(m.group(1))
        for m in _CHAPTER_REF_EN_PATTERN.finditer(text):
            nums.add(m.group(1))
        index_refs = [f"chapter:{n}" for n in sorted(nums, key=lambda x: int(x))]
        if index_refs:
            text = f"{text} {' '.join(index_refs)}"
        obs["steps"].append("index_ref_enhance")
    obs["index_refs"] = index_refs

    normalized = re.sub(r"\s+", " ", text).strip()
    obs["steps"].append("basic_clean")
    obs["normalized_query_text"] = normalized
    return normalized, obs
