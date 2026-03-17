from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.routes.worldbook_route_helpers import (
    _keywords_to_json,
    _list_worldbook_rows,
    _mark_vector_index_dirty,
)
from app.api.routes.worldbook_route_mappers import _build_worldbook_export_all_payload
from app.api.routes.worldbook_route_models import WorldBookImportAllState
from app.core.errors import AppError
from app.db.utils import new_id, utc_now
from app.models.worldbook_entry import WorldBookEntry
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task


def _build_worldbook_export_payload(db: Session, *, project_id: str) -> dict[str, object]:
    return _build_worldbook_export_all_payload(_list_worldbook_rows(db, project_id=project_id))


def _build_worldbook_import_report(
    *,
    dry_run: bool,
    mode: str,
    state: WorldBookImportAllState,
) -> dict[str, object]:
    return {
        'dry_run': bool(dry_run),
        'mode': mode,
        'created': int(state.created),
        'updated': int(state.updated),
        'deleted': int(state.deleted),
        'skipped': int(state.skipped),
        'conflicts': state.conflicts,
        'actions': state.actions,
    }


def _apply_worldbook_import_item(
    db: Session,
    *,
    project_id: str,
    dry_run: bool,
    item: object,
    matches: list[WorldBookEntry],
    state: WorldBookImportAllState,
) -> WorldBookEntry | None:
    key = str(getattr(item, 'title', '') or '').strip()
    if len(matches) > 1:
        state.skipped += 1
        state.conflicts.append({'title': key, 'reason': 'multiple_existing', 'existing_count': len(matches)})
        state.actions.append({'title': key, 'action': 'skip', 'reason': 'multiple_existing'})
        return None

    keywords_json = _keywords_to_json(getattr(item, 'keywords', None))
    if not matches:
        state.created += 1
        state.actions.append({'title': key, 'action': 'create'})
        if dry_run:
            return None

        row = WorldBookEntry(
            id=new_id(),
            project_id=project_id,
            title=item.title,
            content_md=item.content_md or '',
            enabled=bool(item.enabled),
            constant=bool(item.constant),
            keywords_json=keywords_json,
            exclude_recursion=bool(item.exclude_recursion),
            prevent_recursion=bool(item.prevent_recursion),
            char_limit=int(item.char_limit),
            priority=str(item.priority),
        )
        db.add(row)
        db.flush()
        return row

    row = matches[0]
    state.updated += 1
    state.actions.append({'title': key, 'action': 'update', 'entry_id': row.id})
    if dry_run:
        return row

    row.content_md = item.content_md or ''
    row.enabled = bool(item.enabled)
    row.constant = bool(item.constant)
    row.keywords_json = keywords_json
    row.exclude_recursion = bool(item.exclude_recursion)
    row.prevent_recursion = bool(item.prevent_recursion)
    row.char_limit = int(item.char_limit)
    row.priority = str(item.priority)
    row.updated_at = utc_now()
    return row


def _build_worldbook_import_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    body: object,
) -> dict[str, object]:
    if str(getattr(body, 'schema_version', '') or '').strip() != 'worldbook_export_all_v1':
        raise AppError.validation(
            details={
                'reason': 'unsupported_schema_version',
                'schema_version': getattr(body, 'schema_version', None),
            }
        )

    existing = _list_worldbook_rows(db, project_id=project_id)
    by_title: dict[str, list[WorldBookEntry]] = {}
    for row in existing:
        key = str(row.title or '').strip()
        by_title.setdefault(key, []).append(row)

    state = WorldBookImportAllState()
    mode = str(getattr(body, 'mode', 'merge') or 'merge').strip()
    dry_run = bool(getattr(body, 'dry_run', False))

    if mode == 'overwrite':
        state.deleted = len(existing)
        state.actions.append(
            {
                'action': 'delete_all',
                'existing': int(state.deleted),
                'incoming': len(getattr(body, 'entries', None) or []),
            }
        )
        if not dry_run:
            for row in existing:
                db.delete(row)
            db.flush()
        by_title = {}

    for item in getattr(body, 'entries', None) or []:
        key = str(getattr(item, 'title', '') or '').strip()
        row = _apply_worldbook_import_item(
            db,
            project_id=project_id,
            dry_run=dry_run,
            item=item,
            matches=by_title.get(key) or [],
            state=state,
        )
        if row is not None:
            by_title[key] = [row]

    if dry_run:
        return _build_worldbook_import_report(dry_run=True, mode=mode, state=state)

    if state.created or state.updated or state.deleted:
        _mark_vector_index_dirty(db, project_id=project_id)

    db.commit()
    schedule_vector_rebuild_task(
        db=db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_import',
    )
    schedule_search_rebuild_task(
        db=db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason='worldbook_import',
    )
    return _build_worldbook_import_report(dry_run=False, mode=mode, state=state)
