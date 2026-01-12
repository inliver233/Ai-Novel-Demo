from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def _trigger_entries(
    entries: list[WorldBookEntry],
    *,
    query_text: str,
    include_constant: bool,
    enable_recursion: bool,
) -> _TriggerState:
    enabled_entries = [e for e in entries if bool(e.enabled)]
    query = (query_text or "").lower()

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
            matched = next((k for k in keywords if _keyword_matches(base=base, keyword=k)), None)
            if matched is None:
                next_pending.append(e)
                continue

            triggered_ids.add(e.id)
            reason_by_id[e.id] = f"keyword:{matched}"
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
    triggered_entries = [e for e in entries if e.id in reason_by_id]
    triggered_entries.sort(
        key=lambda e: (
            0 if bool(e.constant) else 1,
            -_priority_rank(e.priority),
            -(e.updated_at.timestamp() if e.updated_at else 0),
            e.title or "",
            e.id,
        )
    )

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
    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )

    state = _trigger_entries(
        rows,
        query_text=query_text,
        include_constant=include_constant,
        enable_recursion=enable_recursion,
    )

    text_md, truncated = _format_worldbook_text(rows, reason_by_id=state.reason_by_id, char_limit=int(char_limit))
    triggered = []
    for e in rows:
        reason = state.reason_by_id.get(e.id)
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
