from __future__ import annotations

import json
from typing import Any

from app.models.story_memory import StoryMemory


def _safe_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _safe_json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    return value


def _is_valid_span(position: int, length: int, *, text_len: int) -> bool:
    if position < 0 or length <= 0:
        return False
    if position >= text_len:
        return False
    return position + length <= text_len


def _normalize_search_text(text: str, *, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _candidate_needles(annotation: dict[str, Any]) -> list[str]:
    metadata = annotation.get("metadata") if isinstance(annotation.get("metadata"), dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    candidates: list[str] = []
    for key in ("keyword", "excerpt", "needle"):
        v = metadata.get(key)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    title = annotation.get("title")
    if isinstance(title, str) and title.strip():
        candidates.append(title.strip())

    content = annotation.get("content")
    if isinstance(content, str) and content.strip():
        flat = " ".join(content.strip().split())
        candidates.append(flat[:80].strip())

    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= 4:
            break
    return out


def apply_position_fallback(
    annotations: list[dict[str, Any]],
    *,
    content_md: str,
    max_attempts: int = 40,
    max_scan_chars: int = 20000,
) -> dict[str, int]:
    full_text = content_md or ""
    full_len = len(full_text)
    search_text = _normalize_search_text(full_text, max_len=int(max_scan_chars))
    search_len = len(search_text)
    stats = {"need_fallback": 0, "attempted": 0, "found": 0, "clamped": int(full_len > search_len)}
    if not search_text:
        return stats

    attempts = 0
    for ann in annotations:
        if not isinstance(ann, dict):
            continue

        raw_pos = ann.get("position")
        raw_len = ann.get("length")
        position = int(raw_pos) if isinstance(raw_pos, int) else -1
        length = int(raw_len) if isinstance(raw_len, int) else 0

        if _is_valid_span(position, length, text_len=full_len):
            continue

        stats["need_fallback"] += 1
        if attempts >= int(max_attempts):
            ann["position"] = -1
            ann["length"] = 0
            continue

        attempts += 1
        stats["attempted"] += 1

        found = False
        used = ""
        idx = -1
        used_len = 0
        for needle in _candidate_needles(ann):
            if len(needle) < 2:
                continue

            trimmed = needle
            if len(trimmed) > 80:
                trimmed = trimmed[:80].strip()
            if not trimmed:
                continue

            pos = search_text.find(trimmed)
            if pos < 0 and len(trimmed) > 20:
                pos = search_text.find(trimmed[:20])
                if pos >= 0:
                    trimmed = trimmed[:20]

            if pos >= 0:
                idx = pos
                used = trimmed
                used_len = len(trimmed)
                found = True
                break

        if found and idx >= 0:
            ann["position"] = int(idx)
            ann["length"] = int(used_len)
            meta = ann.get("metadata") if isinstance(ann.get("metadata"), dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            meta = dict(meta)
            meta["position_fallback"] = {"attempted": True, "found": True, "needle": used}
            ann["metadata"] = meta
            stats["found"] += 1
        else:
            ann["position"] = -1
            ann["length"] = 0
            meta = ann.get("metadata") if isinstance(ann.get("metadata"), dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            meta = dict(meta)
            meta["position_fallback"] = {"attempted": True, "found": False}
            ann["metadata"] = meta

    return stats


def build_annotations_from_story_memories(
    memories: list[StoryMemory],
    *,
    content_md: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    annotations: list[dict[str, Any]] = []
    for m in memories:
        annotations.append(
            {
                "id": m.id,
                "type": m.memory_type,
                "title": m.title,
                "content": m.content,
                "importance": float(m.importance_score),
                "position": int(m.text_position),
                "length": int(m.text_length),
                "tags": _safe_json_list(m.tags_json),
                "metadata": _safe_json_dict(m.metadata_json),
            }
        )

    stats = apply_position_fallback(annotations, content_md=content_md or "")
    return annotations, stats
