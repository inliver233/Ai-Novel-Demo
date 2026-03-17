from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.worldbook_route_mappers import _worldbook_entry_to_out
from app.core.errors import AppError
from app.db.utils import new_id
from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry


def _list_worldbook_rows(db: Session, *, project_id: str) -> list[WorldBookEntry]:
    return (
        db.execute(
            select(WorldBookEntry)
            .where(WorldBookEntry.project_id == project_id)
            .order_by(WorldBookEntry.updated_at.desc())
        )
        .scalars()
        .all()
    )


def _build_worldbook_entries_payload(db: Session, *, project_id: str) -> dict[str, object]:
    return {
        'worldbook_entries': [
            _worldbook_entry_to_out(row)
            for row in _list_worldbook_rows(db, project_id=project_id)
        ]
    }


def _mark_vector_index_dirty(db: Session, *, project_id: str) -> None:
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id)
        db.add(row)
        db.flush()
    row.vector_index_dirty = True


def _normalize_keywords(keywords: list[str] | None) -> list[str]:
    return [item.strip() for item in (keywords or []) if isinstance(item, str) and item.strip()]


def _keywords_to_json(keywords: list[str] | None) -> str:
    normalized = _normalize_keywords(keywords)
    return json.dumps(normalized, ensure_ascii=False) if normalized else '[]'


def _dedupe_entry_ids(entry_ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in entry_ids:
        value = str(raw or '').strip()
        if not value:
            raise AppError.validation('entry_ids 不能包含空值')
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _require_worldbook_rows(
    db: Session,
    *,
    project_id: str,
    entry_ids: list[str],
) -> tuple[list[WorldBookEntry], dict[str, WorldBookEntry]]:
    rows = (
        db.execute(
            select(WorldBookEntry).where(
                WorldBookEntry.project_id == project_id,
                WorldBookEntry.id.in_(entry_ids),
            )
        )
        .scalars()
        .all()
    )
    by_id = {str(row.id): row for row in rows}
    missing_ids = [entry_id for entry_id in entry_ids if entry_id not in by_id]
    if missing_ids:
        raise AppError.not_found('部分 worldbook_entries 不存在', details={'missing_ids': missing_ids})
    return rows, by_id


def _copy_title(title: str) -> str:
    suffix = '（复制）'
    base = str(title or '').strip()
    if not base:
        base = '（无标题）'
    max_len = 255
    if len(base) + len(suffix) <= max_len:
        return base + suffix
    return base[: max(0, max_len - len(suffix))].rstrip() + suffix


def _build_worldbook_entry_row(*, project_id: str, body: object) -> WorldBookEntry:
    return WorldBookEntry(
        id=new_id(),
        project_id=project_id,
        title=body.title,
        content_md=body.content_md or '',
        enabled=bool(body.enabled),
        constant=bool(body.constant),
        keywords_json=_keywords_to_json(getattr(body, 'keywords', None)),
        exclude_recursion=bool(body.exclude_recursion),
        prevent_recursion=bool(body.prevent_recursion),
        char_limit=int(body.char_limit),
        priority=str(body.priority),
    )


def _apply_worldbook_entry_update(*, row: WorldBookEntry, body: object) -> None:
    if getattr(body, 'title', None) is not None:
        row.title = body.title
    if getattr(body, 'content_md', None) is not None:
        row.content_md = body.content_md
    if getattr(body, 'enabled', None) is not None:
        row.enabled = bool(body.enabled)
    if getattr(body, 'constant', None) is not None:
        row.constant = bool(body.constant)
    if getattr(body, 'keywords', None) is not None:
        row.keywords_json = _keywords_to_json(body.keywords)
    if getattr(body, 'exclude_recursion', None) is not None:
        row.exclude_recursion = bool(body.exclude_recursion)
    if getattr(body, 'prevent_recursion', None) is not None:
        row.prevent_recursion = bool(body.prevent_recursion)
    if getattr(body, 'char_limit', None) is not None:
        row.char_limit = int(body.char_limit)
    if getattr(body, 'priority', None) is not None:
        row.priority = str(body.priority)
