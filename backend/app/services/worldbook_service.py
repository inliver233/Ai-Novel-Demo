from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook import WorldBookPreviewTriggerOut, WorldBookTriggeredEntryOut


def _parse_json_list(raw: str | None) -> list[str]:
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


def _lower_nonempty(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = (item or "").strip().lower()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


_ASCII_QUERY_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ALIAS_SPLIT_RE = re.compile(r"[\s,|;]+")


def _extract_ascii_query(text: str) -> str:
    parts = _ASCII_QUERY_RE.findall((text or "").strip().lower())
    return "".join([p for p in parts if p.strip()])


def _split_aliases(keyword: str) -> list[str]:
    k = (keyword or "").strip().lower()
    if not k:
        return []
    if k.startswith("alias:") or k.startswith("aliases:"):
        raw = k.split(":", 1)[1].strip()
    elif "|" in k:
        raw = k
    else:
        return []
    return [p.strip() for p in _ALIAS_SPLIT_RE.split(raw) if p.strip()]


def _parse_regex_allowlist_json(raw: str | None) -> set[str]:
    return set(_lower_nonempty(_parse_json_list((raw or "").strip() or None)))


def _contains_pinyin_match(text: str, query_ascii: str, *, cache: dict[str, tuple[str, str]]) -> bool:
    if not query_ascii:
        return False
    if not text:
        return False
    if not _CJK_RE.search(text):
        return False

    cached = cache.get(text)
    if cached is not None:
        full, abbr = cached
        return query_ascii in full or query_ascii in abbr

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r".*codecs\.open\(\) is deprecated.*",
                module=r"^pypinyin(\..*)?$",
            )
            from pypinyin import Style, lazy_pinyin  # type: ignore[import-not-found]

            full = "".join(lazy_pinyin(text, style=Style.NORMAL, errors="ignore")).lower()
            abbr = "".join(lazy_pinyin(text, style=Style.FIRST_LETTER, errors="ignore")).lower()
    except Exception:
        cache[text] = ("", "")
        return False

    cache[text] = (full, abbr)
    return query_ascii in full or query_ascii in abbr


def _keyword_matches(*, base: str, keyword: str) -> bool:
    k = (keyword or "").strip().lower()
    if not k:
        return False

    if k.startswith("word:"):
        needle = k[len("word:") :].strip()
        if not needle:
            return False
        # ASCII word boundary: avoids "he" matching "the".
        pattern = r"(?<![0-9a-z_])" + re.escape(needle) + r"(?![0-9a-z_])"
        return re.search(pattern, base) is not None

    return k in base


@dataclass(frozen=True, slots=True)
class _TriggerState:
    reason_by_id: dict[str, str]
    triggered_ids: set[str]


def _sort_triggered_entries(entries: list[WorldBookEntry], *, reason_by_id: dict[str, str]) -> list[WorldBookEntry]:
    out = [e for e in entries if e.id in reason_by_id]
    out.sort(
        key=lambda e: (
            0 if bool(e.constant) else 1,
            -_priority_rank(e.priority),
            -(e.updated_at.timestamp() if e.updated_at else 0),
            e.title or "",
            e.id,
        )
    )
    return out


def _apply_trigger_limit(entries: list[WorldBookEntry], *, reason_by_id: dict[str, str], limit: int) -> dict[str, str]:
    if limit <= 0:
        return reason_by_id
    keep = {e.id for e in _sort_triggered_entries(entries, reason_by_id=reason_by_id)[:limit]}
    return {k: v for k, v in reason_by_id.items() if k in keep}


def _trigger_entries(
    entries: list[WorldBookEntry],
    *,
    query_text: str,
    include_constant: bool,
    enable_recursion: bool,
) -> _TriggerState:
    enabled_entries = [e for e in entries if bool(e.enabled)]
    query = (query_text or "").lower()

    alias_enabled = bool(getattr(settings, "worldbook_match_alias_enabled", False))
    pinyin_enabled = bool(getattr(settings, "worldbook_match_pinyin_enabled", False))
    regex_enabled = bool(getattr(settings, "worldbook_match_regex_enabled", False))
    regex_allowlist = _parse_regex_allowlist_json(getattr(settings, "worldbook_match_regex_allowlist_json", None))
    pinyin_query = _extract_ascii_query(query_text) if pinyin_enabled else ""
    pinyin_cache: dict[str, tuple[str, str]] = {}

    reason_by_id: dict[str, str] = {}
    triggered_ids: set[str] = set()
    if include_constant:
        for e in enabled_entries:
            if bool(e.constant):
                triggered_ids.add(e.id)
                reason_by_id[e.id] = "constant"

    pending = [e for e in enabled_entries if e.id not in triggered_ids]

    max_passes = max(1, len(pending) + 1)
    for pass_idx in range(max_passes):
        recursion_text = ""
        if enable_recursion and triggered_ids:
            parts = []
            for e in enabled_entries:
                if e.id not in triggered_ids:
                    continue
                if bool(e.prevent_recursion):
                    continue
                content = (e.content_md or "").strip()
                if content:
                    parts.append(content)
            recursion_text = "\n".join(parts).lower()

        search_text = query
        if enable_recursion and recursion_text:
            search_text = (query + "\n" + recursion_text).strip()

        changed = False
        next_pending: list[WorldBookEntry] = []
        for e in pending:
            keywords = _lower_nonempty(_parse_json_list(e.keywords_json))
            if not keywords:
                next_pending.append(e)
                continue

            base = query if bool(e.exclude_recursion) else search_text
            matched_reason: str | None = None
            for k in keywords:
                if _keyword_matches(base=base, keyword=k):
                    matched_reason = f"keyword:{k}"
                    break

                if alias_enabled:
                    for alias in _split_aliases(k):
                        if _keyword_matches(base=base, keyword=alias):
                            matched_reason = f"alias:{alias}"
                            break
                    if matched_reason:
                        break

                if regex_enabled and regex_allowlist and (k.startswith("re:") or k.startswith("regex:")):
                    pattern = k.split(":", 1)[1].strip()
                    if pattern and pattern in regex_allowlist:
                        try:
                            if re.search(pattern, base) is not None:
                                matched_reason = f"regex:{pattern}"
                                break
                        except Exception:
                            pass

                if pinyin_query and pinyin_enabled and _contains_pinyin_match(k, pinyin_query, cache=pinyin_cache):
                    matched_reason = f"pinyin:{k}"
                    break

            if matched_reason is None:
                next_pending.append(e)
                continue

            triggered_ids.add(e.id)
            reason_by_id[e.id] = matched_reason
            changed = True

        pending = next_pending
        if not enable_recursion:
            break
        if not changed:
            break
        if not pending:
            break
        if pass_idx >= max_passes - 1:
            break

    return _TriggerState(reason_by_id=reason_by_id, triggered_ids=triggered_ids)


def _priority_rank(value: str | None) -> int:
    v = str(value or "").strip().lower()
    if v == "must":
        return 3
    if v == "important":
        return 2
    if v == "optional":
        return 1
    return 0


def _format_worldbook_text(entries: list[WorldBookEntry], *, reason_by_id: dict[str, str], char_limit: int) -> tuple[str, bool]:
    triggered_entries = _sort_triggered_entries(entries, reason_by_id=reason_by_id)
    parts: list[str] = []
    for e in triggered_entries:
        title = (e.title or "").strip() or "Untitled"
        reason = reason_by_id.get(e.id) or "unknown"
        content = (e.content_md or "").strip()
        limit = int(e.char_limit or 0)
        if limit >= 0 and len(content) > limit:
            content = content[:limit].rstrip()
        header = f"【世界书条目：{title} | {reason} | priority:{str(e.priority or 'important')}】"
        parts.append(f"{header}\n{content}".rstrip())

    inner = "\n\n---\n\n".join([p for p in parts if p.strip()]).strip()
    truncated = False
    if char_limit >= 0 and inner and len(inner) > char_limit:
        inner = inner[:char_limit].rstrip()
        truncated = True
    if not inner:
        return "", False
    return f"<WORLD_BOOK>\n{inner}\n</WORLD_BOOK>", truncated


def preview_worldbook_trigger(
    *,
    db: Session,
    project_id: str,
    query_text: str,
    include_constant: bool,
    enable_recursion: bool,
    char_limit: int,
) -> WorldBookPreviewTriggerOut:
    effective_query_text = query_text
    if bool(getattr(settings, "glossary_query_expand_enabled", False)):
        try:
            from app.services.glossary_service import expand_query_text_with_glossary

            effective_query_text, _obs = expand_query_text_with_glossary(
                db=db,
                project_id=project_id,
                query_text=query_text,
            )
        except Exception:
            effective_query_text = query_text

    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )

    state = _trigger_entries(
        rows,
        query_text=effective_query_text,
        include_constant=include_constant,
        enable_recursion=enable_recursion,
    )

    enhanced_enabled = (
        bool(getattr(settings, "worldbook_match_alias_enabled", False))
        or bool(getattr(settings, "worldbook_match_pinyin_enabled", False))
        or bool(getattr(settings, "worldbook_match_regex_enabled", False))
    )
    max_entries = int(getattr(settings, "worldbook_match_max_triggered_entries", 0) or 0)
    max_entries = max(0, max_entries)
    reason_by_id = (
        _apply_trigger_limit(rows, reason_by_id=state.reason_by_id, limit=max_entries) if (enhanced_enabled and max_entries) else state.reason_by_id
    )

    text_md, truncated = _format_worldbook_text(rows, reason_by_id=reason_by_id, char_limit=int(char_limit))
    triggered: list[WorldBookTriggeredEntryOut] = []
    for e in _sort_triggered_entries(rows, reason_by_id=reason_by_id):
        reason = reason_by_id.get(e.id)
        if not reason:
            continue
        triggered.append(
            WorldBookTriggeredEntryOut(
                id=e.id,
                title=e.title,
                reason=reason,
                priority=str(e.priority or "important"),  # type: ignore[arg-type]
            )
        )

    return WorldBookPreviewTriggerOut(triggered=triggered, text_md=text_md, truncated=truncated)
