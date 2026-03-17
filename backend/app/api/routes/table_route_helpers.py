from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.table_route_mappers import _row_public, _safe_json_loads, _table_public
from app.core.errors import AppError
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.project_table import ProjectTable, ProjectTableRow
from app.services.project_seed_service import ensure_default_numeric_tables
from app.services.table_ai_update_service import schedule_table_ai_update_task
from app.services.table_executor import normalize_schema, validate_row_data

_TABLE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class _TableAiUpdateTarget:
    chapter_id: str | None
    chapter_token: str


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _project_has_tables(db: Session, *, project_id: str) -> bool:
    return (
        db.execute(select(ProjectTable.id).where(ProjectTable.project_id == project_id).limit(1)).scalars().first()
        is not None
    )


def _require_project_table(db: Session, *, project_id: str, table_id: str) -> ProjectTable:
    table = db.get(ProjectTable, table_id)
    if table is None or str(table.project_id) != str(project_id):
        raise AppError.not_found()
    return table


def _require_project_table_row(
    db: Session,
    *,
    project_id: str,
    table_id: str,
    row_id: str,
) -> ProjectTableRow:
    row = db.get(ProjectTableRow, row_id)
    if row is None or str(row.project_id) != str(project_id) or str(row.table_id) != str(table_id):
        raise AppError.not_found()
    return row


def _count_table_rows(db: Session, *, table_id: str) -> int:
    return int(
        db.execute(select(func.count()).select_from(ProjectTableRow).where(ProjectTableRow.table_id == table_id)).scalar()
        or 0
    )


def _normalize_table_name(name: str | None) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        raise AppError.validation(message="name 不能为空")
    return normalized


def _normalize_table_key(table_key: str | None) -> str:
    requested = str(table_key or "").strip()
    if requested:
        if not _TABLE_KEY_RE.match(requested):
            raise AppError.validation(message="table_key 仅允许字母数字_- 且长度<=64")
        return requested
    return f"tbl_{new_id()[:8]}"


def _load_table_schema(*, table: ProjectTable, table_id: str) -> dict[str, Any]:
    schema_obj = _safe_json_loads(table.schema_json)
    if not isinstance(schema_obj, dict):
        raise AppError.validation(message="table.schema_json 非法", details={"table_id": table_id})
    return schema_obj


def _build_project_tables_payload(
    db: Session,
    *,
    project_id: str,
    include_schema: bool,
    seed_defaults: bool,
) -> dict[str, object]:
    if seed_defaults and not _project_has_tables(db, project_id=project_id):
        ensure_default_numeric_tables(db, project_id=project_id)

    tables = (
        db.execute(
            select(ProjectTable)
            .where(ProjectTable.project_id == project_id)
            .order_by(ProjectTable.updated_at.desc(), ProjectTable.id.desc())
        )
        .scalars()
        .all()
    )
    counts = dict(
        db.execute(
            select(ProjectTableRow.table_id, func.count())
            .where(ProjectTableRow.project_id == project_id)
            .group_by(ProjectTableRow.table_id)
        ).all()
    )
    return {
        "tables": [_table_public(table, include_schema=include_schema, row_count=int(counts.get(table.id, 0))) for table in tables]
    }


def _create_project_table_payload(
    db: Session,
    *,
    project_id: str,
    body: object,
) -> dict[str, object]:
    row = ProjectTable(
        id=new_id(),
        project_id=project_id,
        table_key=_normalize_table_key(getattr(body, "table_key", None)),
        name=_normalize_table_name(getattr(body, "name", None)),
        auto_update_enabled=bool(getattr(body, "auto_update_enabled", None))
        if getattr(body, "auto_update_enabled", None) is not None
        else True,
        schema_version=1,
        schema_json=_compact_json_dumps(normalize_schema(getattr(body, "table_schema"))),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict("table_key 已存在") from None
    db.refresh(row)
    return {"table": _table_public(row, include_schema=True, row_count=0)}


def _build_project_table_payload(
    db: Session,
    *,
    table: ProjectTable,
    include_schema: bool,
) -> dict[str, object]:
    return {"table": _table_public(table, include_schema=include_schema, row_count=_count_table_rows(db, table_id=table.id))}


def _update_project_table_payload(
    db: Session,
    *,
    table: ProjectTable,
    body: object,
) -> dict[str, object]:
    name = getattr(body, "name", None)
    if name is not None:
        table.name = _normalize_table_name(name)

    auto_update_enabled = getattr(body, "auto_update_enabled", None)
    if auto_update_enabled is not None:
        table.auto_update_enabled = bool(auto_update_enabled)

    table_schema = getattr(body, "table_schema", None)
    if table_schema is not None:
        schema_norm = normalize_schema(table_schema)
        rows = (
            db.execute(
                select(ProjectTableRow)
                .where(ProjectTableRow.table_id == table.id)
                .order_by(ProjectTableRow.row_index.asc(), ProjectTableRow.id.asc())
            )
            .scalars()
            .all()
        )
        for row in rows:
            data_obj = _safe_json_loads(row.data_json)
            if not isinstance(data_obj, dict):
                raise AppError.validation(message="存在非法 row.data_json", details={"row_id": row.id})
            try:
                validate_row_data(schema=schema_norm, data=data_obj)
            except AppError as exc:
                raise AppError.validation(
                    message="schema 更新会导致现有行不兼容",
                    details={"row_id": row.id, "error": exc.details},
                ) from None

        table.schema_json = _compact_json_dumps(schema_norm)
        table.schema_version = int(table.schema_version or 1) + 1

    db.commit()
    db.refresh(table)
    return {"table": _table_public(table, include_schema=True, row_count=_count_table_rows(db, table_id=table.id))}


def _build_project_table_rows_payload(
    db: Session,
    *,
    table: ProjectTable,
    offset: int,
    limit: int,
) -> dict[str, object]:
    rows = (
        db.execute(
            select(ProjectTableRow)
            .where(ProjectTableRow.table_id == table.id)
            .order_by(ProjectTableRow.row_index.asc(), ProjectTableRow.id.asc())
            .offset(int(offset))
            .limit(int(limit))
        )
        .scalars()
        .all()
    )
    return {
        "rows": [_row_public(row) for row in rows],
        "total": _count_table_rows(db, table_id=table.id),
        "offset": int(offset),
        "returned": len(rows),
    }


def _next_table_row_index(db: Session, *, table_id: str) -> int:
    max_idx = db.execute(select(func.max(ProjectTableRow.row_index)).where(ProjectTableRow.table_id == table_id)).scalar()
    return int(max_idx or 0) + 1


def _create_project_table_row_payload(
    db: Session,
    *,
    project_id: str,
    table: ProjectTable,
    body: object,
) -> dict[str, object]:
    data_norm = validate_row_data(schema=_load_table_schema(table=table, table_id=table.id), data=getattr(body, "data"))
    row = ProjectTableRow(
        id=new_id(),
        project_id=project_id,
        table_id=table.id,
        row_index=_next_table_row_index(db, table_id=table.id),
        data_json=_compact_json_dumps(data_norm),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"row": _row_public(row)}


def _update_project_table_row_payload(
    db: Session,
    *,
    table: ProjectTable,
    row: ProjectTableRow,
    body: object,
) -> dict[str, object]:
    data_norm = validate_row_data(schema=_load_table_schema(table=table, table_id=table.id), data=getattr(body, "data"))
    row.data_json = _compact_json_dumps(data_norm)
    db.commit()
    db.refresh(row)
    return {"row": _row_public(row)}


def _delete_project_table_payload(db: Session, *, table: ProjectTable) -> dict[str, object]:
    db.delete(table)
    db.commit()
    return {"deleted": True}


def _delete_project_table_row_payload(db: Session, *, row: ProjectTableRow) -> dict[str, object]:
    db.delete(row)
    db.commit()
    return {"deleted": True}


def _resolve_table_ai_update_target(
    db: Session,
    *,
    project_id: str,
    chapter_id: str | None,
) -> _TableAiUpdateTarget:
    chapter: Chapter | None = None
    if chapter_id is not None and str(chapter_id).strip():
        chapter = db.get(Chapter, str(chapter_id))
        if chapter is None or str(getattr(chapter, "project_id", "")) != str(project_id):
            raise AppError.not_found("章节不存在")
        if str(getattr(chapter, "status", "") or "") != "done":
            raise AppError.validation(details={"reason": "chapter_not_done"})
    else:
        chapter = (
            db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id, Chapter.status == "done")
                .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    resolved_id = str(getattr(chapter, "id", "") or "").strip() or None
    updated_at = getattr(chapter, "updated_at", None) if chapter is not None else None
    token = (
        updated_at.isoformat().replace("+00:00", "Z")
        if updated_at is not None
        else utc_now().isoformat().replace("+00:00", "Z")
    )
    return _TableAiUpdateTarget(chapter_id=resolved_id, chapter_token=token)


def _schedule_project_table_ai_update_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    table: ProjectTable,
    focus: str | None,
    chapter_id: str | None,
) -> dict[str, object]:
    target = _resolve_table_ai_update_target(db, project_id=project_id, chapter_id=chapter_id)
    task_id = schedule_table_ai_update_task(
        db=db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        table_id=table.id,
        chapter_id=target.chapter_id,
        chapter_token=target.chapter_token,
        focus=focus,
        reason="manual_table_ai_update",
    )
    if not task_id:
        raise AppError.validation(details={"reason": "schedule_failed"})
    return {"task_id": task_id, "chapter_id": target.chapter_id, "table_id": table.id}
