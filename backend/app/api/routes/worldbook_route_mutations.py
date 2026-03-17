from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.routes.worldbook_route_helpers import (
    _apply_worldbook_entry_update,
    _build_worldbook_entry_row,
    _copy_title,
    _dedupe_entry_ids,
    _mark_vector_index_dirty,
    _require_worldbook_rows,
)
from app.core.errors import AppError
from app.api.routes.worldbook_route_mappers import _worldbook_entry_to_out
from app.db.utils import new_id
from app.models.worldbook_entry import WorldBookEntry
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task


def _schedule_worldbook_rebuilds(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    reason: str,
) -> None:
    schedule_vector_rebuild_task(
        db=db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason=reason,
    )
    schedule_search_rebuild_task(
        db=db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason=reason,
    )


def _validate_worldbook_bulk_update_body(body: object) -> None:
    if (
        getattr(body, 'enabled', None) is None
        and getattr(body, 'constant', None) is None
        and getattr(body, 'exclude_recursion', None) is None
        and getattr(body, 'prevent_recursion', None) is None
        and getattr(body, 'char_limit', None) is None
        and getattr(body, 'priority', None) is None
    ):
        raise AppError.validation('至少提供一个更新字段')


def _build_worldbook_bulk_update_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    body: object,
) -> dict[str, object]:
    _validate_worldbook_bulk_update_body(body)
    entry_ids = _dedupe_entry_ids(body.entry_ids)
    rows, by_id = _require_worldbook_rows(db, project_id=project_id, entry_ids=entry_ids)

    for row in rows:
        if body.enabled is not None:
            row.enabled = bool(body.enabled)
        if body.constant is not None:
            row.constant = bool(body.constant)
        if body.exclude_recursion is not None:
            row.exclude_recursion = bool(body.exclude_recursion)
        if body.prevent_recursion is not None:
            row.prevent_recursion = bool(body.prevent_recursion)
        if body.char_limit is not None:
            row.char_limit = int(body.char_limit)
        if body.priority is not None:
            row.priority = str(body.priority)

    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    for row in rows:
        db.refresh(row)

    _schedule_worldbook_rebuilds(
        db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_bulk_update',
    )
    return {'worldbook_entries': [_worldbook_entry_to_out(by_id[entry_id]) for entry_id in entry_ids]}


def _build_worldbook_bulk_delete_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    body: object,
) -> dict[str, object]:
    entry_ids = _dedupe_entry_ids(body.entry_ids)
    rows, _ = _require_worldbook_rows(db, project_id=project_id, entry_ids=entry_ids)
    for row in rows:
        db.delete(row)

    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    _schedule_worldbook_rebuilds(
        db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_bulk_delete',
    )
    return {'deleted_ids': entry_ids}


def _build_worldbook_duplicate_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    body: object,
) -> dict[str, object]:
    entry_ids = _dedupe_entry_ids(body.entry_ids)
    _, by_id = _require_worldbook_rows(db, project_id=project_id, entry_ids=entry_ids)

    created: list[WorldBookEntry] = []
    for source_id in entry_ids:
        src = by_id[source_id]
        created.append(
            WorldBookEntry(
                id=new_id(),
                project_id=project_id,
                title=_copy_title(str(src.title or '')),
                content_md=str(src.content_md or ''),
                enabled=bool(src.enabled),
                constant=bool(src.constant),
                keywords_json=src.keywords_json,
                exclude_recursion=bool(src.exclude_recursion),
                prevent_recursion=bool(src.prevent_recursion),
                char_limit=int(src.char_limit or 0),
                priority=str(src.priority or 'important'),
            )
        )

    db.add_all(created)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    for row in created:
        db.refresh(row)

    _schedule_worldbook_rebuilds(
        db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_duplicate',
    )
    return {'worldbook_entries': [_worldbook_entry_to_out(row) for row in created]}


def _build_worldbook_create_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    body: object,
) -> dict[str, object]:
    row = _build_worldbook_entry_row(project_id=project_id, body=body)
    db.add(row)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    db.refresh(row)
    _schedule_worldbook_rebuilds(
        db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_create',
    )
    return {'worldbook_entry': _worldbook_entry_to_out(row)}


def _build_worldbook_update_payload(
    db: Session,
    *,
    row: WorldBookEntry,
    actor_user_id: str,
    request_id: str,
    body: object,
) -> dict[str, object]:
    _apply_worldbook_entry_update(row=row, body=body)
    _mark_vector_index_dirty(db, project_id=str(row.project_id))
    db.commit()
    db.refresh(row)
    _schedule_worldbook_rebuilds(
        db,
        project_id=str(row.project_id),
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_update',
    )
    return {'worldbook_entry': _worldbook_entry_to_out(row)}


def _build_worldbook_delete_payload(
    db: Session,
    *,
    row: WorldBookEntry,
    actor_user_id: str,
    request_id: str,
) -> dict[str, object]:
    project_id = str(row.project_id)
    db.delete(row)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    _schedule_worldbook_rebuilds(
        db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_delete',
    )
    return {}
