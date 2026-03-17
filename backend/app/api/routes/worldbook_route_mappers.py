from __future__ import annotations

import json

from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook import WorldBookEntryOut, WorldBookExportAllOut, WorldBookExportEntryV1


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


def _worldbook_entry_to_out(row: WorldBookEntry) -> dict[str, object]:
    return WorldBookEntryOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=row.content_md or '',
        enabled=bool(row.enabled),
        constant=bool(row.constant),
        keywords=_parse_json_list(row.keywords_json),
        exclude_recursion=bool(row.exclude_recursion),
        prevent_recursion=bool(row.prevent_recursion),
        char_limit=int(row.char_limit or 0),
        priority=str(row.priority or 'important'),  # type: ignore[arg-type]
        updated_at=row.updated_at,
    ).model_dump()


def _worldbook_export_entry_from_row(row: WorldBookEntry) -> WorldBookExportEntryV1:
    return WorldBookExportEntryV1(
        title=row.title,
        content_md=row.content_md or '',
        enabled=bool(row.enabled),
        constant=bool(row.constant),
        keywords=_parse_json_list(row.keywords_json),
        exclude_recursion=bool(row.exclude_recursion),
        prevent_recursion=bool(row.prevent_recursion),
        char_limit=int(row.char_limit or 0),
        priority=str(row.priority or 'important'),  # type: ignore[arg-type]
    )


def _build_worldbook_export_all_payload(rows: list[WorldBookEntry]) -> dict[str, object]:
    return {
        'export': WorldBookExportAllOut(
            entries=[_worldbook_export_entry_from_row(row) for row in rows]
        ).model_dump()
    }
