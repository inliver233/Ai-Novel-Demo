from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes.memory_route_helpers import _parse_iso_dt
from app.api.routes.memory_route_structured_mappers import (
    _map_memory_entity_row,
    _map_memory_evidence_row,
    _map_memory_event_row,
    _map_memory_foreshadow_row,
    _map_memory_relation_row,
)
from app.api.routes.memory_route_structured_models import (
    STRUCTURED_MEMORY_TABLES,
    StructuredMemoryQueryArgs,
    StructuredMemoryTableName,
    StructuredMemoryTablePage,
)
from app.core.errors import AppError
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryEvent, MemoryForeshadow, MemoryRelation

StructuredRowMapper = Callable[[Any], dict[str, object]]


@dataclass(frozen=True)
class _StructuredMemoryTableSpec:
    model: type[Any]
    search_columns: tuple[Any, ...]
    before_column: Any
    order_by: tuple[Any, ...]
    cursor_attr: str
    mapper: StructuredRowMapper


_STRUCTURED_MEMORY_TABLE_SPECS: dict[StructuredMemoryTableName, _StructuredMemoryTableSpec] = {
    "entities": _StructuredMemoryTableSpec(
        model=MemoryEntity,
        search_columns=(MemoryEntity.name, MemoryEntity.summary_md, MemoryEntity.entity_type),
        before_column=MemoryEntity.updated_at,
        order_by=(MemoryEntity.updated_at.desc(), MemoryEntity.id.desc()),
        cursor_attr="updated_at",
        mapper=_map_memory_entity_row,
    ),
    "relations": _StructuredMemoryTableSpec(
        model=MemoryRelation,
        search_columns=(MemoryRelation.relation_type, MemoryRelation.description_md),
        before_column=MemoryRelation.updated_at,
        order_by=(MemoryRelation.updated_at.desc(), MemoryRelation.id.desc()),
        cursor_attr="updated_at",
        mapper=_map_memory_relation_row,
    ),
    "events": _StructuredMemoryTableSpec(
        model=MemoryEvent,
        search_columns=(MemoryEvent.title, MemoryEvent.content_md, MemoryEvent.event_type),
        before_column=MemoryEvent.updated_at,
        order_by=(MemoryEvent.updated_at.desc(), MemoryEvent.id.desc()),
        cursor_attr="updated_at",
        mapper=_map_memory_event_row,
    ),
    "foreshadows": _StructuredMemoryTableSpec(
        model=MemoryForeshadow,
        search_columns=(MemoryForeshadow.title, MemoryForeshadow.content_md),
        before_column=MemoryForeshadow.updated_at,
        order_by=(MemoryForeshadow.updated_at.desc(), MemoryForeshadow.id.desc()),
        cursor_attr="updated_at",
        mapper=_map_memory_foreshadow_row,
    ),
    "evidence": _StructuredMemoryTableSpec(
        model=MemoryEvidence,
        search_columns=(MemoryEvidence.quote_md, MemoryEvidence.source_type, MemoryEvidence.source_id),
        before_column=MemoryEvidence.created_at,
        order_by=(MemoryEvidence.created_at.desc(), MemoryEvidence.id.desc()),
        cursor_attr="created_at",
        mapper=_map_memory_evidence_row,
    ),
}


def _normalize_structured_memory_args(
    *,
    table: str | None,
    q: str | None,
    before: str | None,
    limit: int,
) -> StructuredMemoryQueryArgs:
    table_norm = str(table or "").strip().lower() or None
    if table_norm is not None and table_norm not in STRUCTURED_MEMORY_TABLES:
        raise AppError.validation(details={"reason": "invalid_table", "table": table})

    keyword = str(q or "").strip() or None
    pattern = f"%{keyword}%" if keyword else None

    before_dt = None
    if table_norm is not None and before is not None:
        before_dt = _parse_iso_dt(before)
        if before_dt is None:
            raise AppError.validation(details={"reason": "invalid_before", "before": before})

    return StructuredMemoryQueryArgs(
        table=table_norm,
        keyword=keyword,
        pattern=pattern,
        before=before,
        before_dt=before_dt,
        limit=int(limit),
    )


def _get_structured_memory_table_spec(table_name: StructuredMemoryTableName) -> _StructuredMemoryTableSpec:
    spec = _STRUCTURED_MEMORY_TABLE_SPECS.get(table_name)
    if spec is None:
        raise AppError.validation(details={"reason": "invalid_table", "table": table_name})
    return spec


def _build_structured_memory_filters(
    *,
    spec: _StructuredMemoryTableSpec,
    project_id: str,
    include_deleted: bool,
    pattern: str | None,
) -> list[Any]:
    filters = [spec.model.project_id == project_id]
    if not include_deleted:
        filters.append(spec.model.deleted_at.is_(None))
    if pattern:
        filters.append(or_(*(column.like(pattern) for column in spec.search_columns)))
    return filters


def _count_structured_memory_rows(
    db: Session,
    *,
    project_id: str,
    table_name: StructuredMemoryTableName,
    include_deleted: bool,
    pattern: str | None,
) -> int:
    spec = _get_structured_memory_table_spec(table_name)
    filters = _build_structured_memory_filters(
        spec=spec,
        project_id=project_id,
        include_deleted=include_deleted,
        pattern=pattern,
    )
    return int(db.execute(select(func.count()).select_from(spec.model).where(*filters)).scalar_one())


def _list_structured_memory_table_page(
    db: Session,
    *,
    project_id: str,
    table_name: StructuredMemoryTableName,
    include_deleted: bool,
    pattern: str | None,
    before_dt: Any,
    limit: int,
) -> StructuredMemoryTablePage:
    spec = _get_structured_memory_table_spec(table_name)
    filters = _build_structured_memory_filters(
        spec=spec,
        project_id=project_id,
        include_deleted=include_deleted,
        pattern=pattern,
    )
    query = select(spec.model).where(*filters)
    if before_dt is not None:
        query = query.where(spec.before_column < before_dt)
    rows = db.execute(query.order_by(*spec.order_by).limit(int(limit) + 1)).scalars().all()
    has_more = len(rows) > int(limit)
    rows = rows[: int(limit)]

    cursor = None
    if has_more and rows:
        cursor_value = getattr(rows[-1], spec.cursor_attr, None)
        cursor = cursor_value.isoformat() if cursor_value else None

    return StructuredMemoryTablePage(items=[spec.mapper(row) for row in rows], cursor=cursor)


def _build_structured_memory_payload(
    db: Session,
    *,
    project_id: str,
    include_deleted: bool,
    table: str | None,
    q: str | None,
    before: str | None,
    limit: int,
) -> dict[str, object]:
    args = _normalize_structured_memory_args(table=table, q=q, before=before, limit=limit)
    counts = {
        table_name: _count_structured_memory_rows(
            db,
            project_id=project_id,
            table_name=table_name,
            include_deleted=include_deleted,
            pattern=args.pattern,
        )
        for table_name in STRUCTURED_MEMORY_TABLES
    }

    data: dict[str, object] = {"counts": counts, "cursor": {}, "table": args.table, "q": args.keyword}
    cursors: dict[str, str | None] = {table_name: None for table_name in STRUCTURED_MEMORY_TABLES}

    for table_name in STRUCTURED_MEMORY_TABLES:
        if args.table not in (None, table_name):
            data[table_name] = []
            continue
        page = _list_structured_memory_table_page(
            db,
            project_id=project_id,
            table_name=table_name,
            include_deleted=include_deleted,
            pattern=args.pattern,
            before_dt=args.before_dt if args.table == table_name else None,
            limit=limit,
        )
        data[table_name] = page.items
        cursors[table_name] = page.cursor

    data["cursor"] = cursors
    return data
