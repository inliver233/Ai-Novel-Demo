from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import (
    DbDep,
    UserIdDep,
    require_project_editor,
    require_project_viewer,
    require_worldbook_entry_editor,
)
from app.api.routes.worldbook_route_helpers import (
    _build_worldbook_entries_payload,
    _mark_vector_index_dirty,
)
from app.api.routes.worldbook_route_import_export import (
    _build_worldbook_export_payload,
    _build_worldbook_import_payload,
)
from app.api.routes.worldbook_route_mappers import _parse_json_list, _worldbook_entry_to_out
from app.api.routes.worldbook_route_mutations import (
    _build_worldbook_bulk_delete_payload,
    _build_worldbook_bulk_update_payload,
    _build_worldbook_duplicate_payload,
)
from app.core.config import settings
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook import (
    WorldBookBulkDeleteRequest,
    WorldBookBulkUpdateRequest,
    WorldBookDuplicateRequest,
    WorldBookEntryCreate,
    WorldBookEntryUpdate,
    WorldBookImportAllRequest,
    WorldBookPreviewTriggerRequest,
)
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.project_task_service import schedule_worldbook_auto_update_task
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task
from app.services.worldbook_service import preview_worldbook_trigger

router = APIRouter()


@router.get('/projects/{project_id}/worldbook_entries')
def list_worldbook_entries(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_worldbook_entries_payload(db, project_id=project_id))


@router.post('/projects/{project_id}/worldbook_entries/auto_update')
def trigger_worldbook_auto_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    chapter_id: str | None = Query(default=None, max_length=36),
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    chapter: Chapter | None = None
    if chapter_id is not None and str(chapter_id).strip():
        chapter = db.get(Chapter, str(chapter_id))
        if chapter is None or str(chapter.project_id) != str(project_id):
            raise AppError.not_found('章节不存在')
        if str(getattr(chapter, 'status', '') or '') != 'done':
            raise AppError.validation(details={'reason': 'chapter_not_done'})
    else:
        chapter = (
            db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.status == 'done',
                )
                .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    cid = str(getattr(chapter, 'id', '') or '').strip() or None
    updated_at = getattr(chapter, 'updated_at', None) if chapter is not None else None
    token = (
        updated_at.isoformat().replace('+00:00', 'Z')
        if updated_at is not None
        else utc_now().isoformat().replace('+00:00', 'Z')
    )

    task_id = schedule_worldbook_auto_update_task(
        db=db,
        project_id=project_id,
        actor_user_id=user_id,
        request_id=request_id,
        chapter_id=cid,
        chapter_token=token,
        reason='manual_worldbook_auto_update',
    )
    if not task_id:
        raise AppError.validation(details={'reason': 'schedule_failed'})
    return ok_payload(request_id=request_id, data={'task_id': task_id, 'chapter_id': cid})


@router.get('/projects/{project_id}/worldbook_entries/export_all')
def export_all_worldbook_entries(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_worldbook_export_payload(db, project_id=project_id))


@router.post('/projects/{project_id}/worldbook_entries/import_all')
def import_all_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookImportAllRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_import_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            body=body,
        ),
    )


@router.post('/projects/{project_id}/worldbook_entries/bulk_update')
def bulk_update_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookBulkUpdateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    if (
        body.enabled is None
        and body.constant is None
        and body.exclude_recursion is None
        and body.prevent_recursion is None
        and body.char_limit is None
        and body.priority is None
    ):
        raise AppError.validation('至少提供一个更新字段')

    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_bulk_update_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            body=body,
        ),
    )


@router.post('/projects/{project_id}/worldbook_entries/bulk_delete')
def bulk_delete_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookBulkDeleteRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_bulk_delete_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            body=body,
        ),
    )


@router.post('/projects/{project_id}/worldbook_entries/duplicate')
def duplicate_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookDuplicateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_duplicate_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            body=body,
        ),
    )


@router.post('/projects/{project_id}/worldbook_entries')
def create_worldbook_entry(
    request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: WorldBookEntryCreate
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    keywords = [k.strip() for k in (body.keywords or []) if isinstance(k, str) and k.strip()]
    keywords_json = json.dumps(keywords, ensure_ascii=False) if keywords else '[]'
    row = WorldBookEntry(
        id=new_id(),
        project_id=project_id,
        title=body.title,
        content_md=body.content_md or '',
        enabled=bool(body.enabled),
        constant=bool(body.constant),
        keywords_json=keywords_json,
        exclude_recursion=bool(body.exclude_recursion),
        prevent_recursion=bool(body.prevent_recursion),
        char_limit=int(body.char_limit),
        priority=str(body.priority),
    )
    db.add(row)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(
        db=db,
        project_id=project_id,
        actor_user_id=user_id,
        request_id=request_id,
        reason='worldbook_create',
    )
    schedule_search_rebuild_task(
        db=db,
        project_id=project_id,
        actor_user_id=user_id,
        request_id=request_id,
        reason='worldbook_create',
    )
    return ok_payload(request_id=request_id, data={'worldbook_entry': _worldbook_entry_to_out(row)})


@router.put('/worldbook_entries/{entry_id}')
def update_worldbook_entry(
    request: Request, db: DbDep, user_id: UserIdDep, entry_id: str, body: WorldBookEntryUpdate
) -> dict:
    request_id = request.state.request_id
    row = require_worldbook_entry_editor(db, entry_id=entry_id, user_id=user_id)

    if body.title is not None:
        row.title = body.title
    if body.content_md is not None:
        row.content_md = body.content_md
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.constant is not None:
        row.constant = bool(body.constant)
    if body.keywords is not None:
        keywords = [k.strip() for k in (body.keywords or []) if isinstance(k, str) and k.strip()]
        row.keywords_json = json.dumps(keywords, ensure_ascii=False) if keywords else '[]'
    if body.exclude_recursion is not None:
        row.exclude_recursion = bool(body.exclude_recursion)
    if body.prevent_recursion is not None:
        row.prevent_recursion = bool(body.prevent_recursion)
    if body.char_limit is not None:
        row.char_limit = int(body.char_limit)
    if body.priority is not None:
        row.priority = str(body.priority)

    _mark_vector_index_dirty(db, project_id=str(row.project_id))
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(
        db=db,
        project_id=str(row.project_id),
        actor_user_id=user_id,
        request_id=request_id,
        reason='worldbook_update',
    )
    schedule_search_rebuild_task(
        db=db,
        project_id=str(row.project_id),
        actor_user_id=user_id,
        request_id=request_id,
        reason='worldbook_update',
    )
    return ok_payload(request_id=request_id, data={'worldbook_entry': _worldbook_entry_to_out(row)})


@router.delete('/worldbook_entries/{entry_id}')
def delete_worldbook_entry(request: Request, db: DbDep, user_id: UserIdDep, entry_id: str) -> dict:
    request_id = request.state.request_id
    row = require_worldbook_entry_editor(db, entry_id=entry_id, user_id=user_id)
    db.delete(row)
    _mark_vector_index_dirty(db, project_id=str(row.project_id))
    db.commit()
    schedule_vector_rebuild_task(
        db=db,
        project_id=str(row.project_id),
        actor_user_id=user_id,
        request_id=request_id,
        reason='worldbook_delete',
    )
    schedule_search_rebuild_task(
        db=db,
        project_id=str(row.project_id),
        actor_user_id=user_id,
        request_id=request_id,
        reason='worldbook_delete',
    )
    return ok_payload(request_id=request_id, data={})


@router.post('/projects/{project_id}/worldbook_entries/preview_trigger')
def preview_trigger(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookPreviewTriggerRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    settings_row = db.get(ProjectSettings, project_id)
    qp_cfg = parse_query_preprocessing_config(
        (settings_row.query_preprocessing_json or '').strip() if settings_row is not None else None
    )
    normalized, preprocess_obs = normalize_query_text(query_text=body.query_text, config=qp_cfg)

    result = preview_worldbook_trigger(
        db=db,
        project_id=project_id,
        query_text=normalized,
        include_constant=body.include_constant,
        enable_recursion=body.enable_recursion,
        char_limit=body.char_limit,
    )
    payload = result.model_dump()
    payload['raw_query_text'] = body.query_text
    payload['normalized_query_text'] = normalized
    payload['preprocess_obs'] = preprocess_obs
    payload['match_config'] = {
        'alias_enabled': bool(getattr(settings, 'worldbook_match_alias_enabled', False)),
        'pinyin_enabled': bool(getattr(settings, 'worldbook_match_pinyin_enabled', False)),
        'regex_enabled': bool(getattr(settings, 'worldbook_match_regex_enabled', False)),
        'regex_allowlist_size': len(_parse_json_list(getattr(settings, 'worldbook_match_regex_allowlist_json', None))),
        'max_triggered_entries': int(getattr(settings, 'worldbook_match_max_triggered_entries', 0) or 0),
    }
    return ok_payload(request_id=request_id, data=payload)
