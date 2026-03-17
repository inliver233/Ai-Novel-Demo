from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import (
    DbDep,
    UserIdDep,
    require_project_editor,
    require_project_viewer,
    require_worldbook_entry_editor,
)
from app.api.routes.worldbook_route_helpers import _build_worldbook_entries_payload
from app.api.routes.worldbook_route_import_export import (
    _build_worldbook_export_payload,
    _build_worldbook_import_payload,
)
from app.api.routes.worldbook_route_mutations import (
    _build_worldbook_bulk_delete_payload,
    _build_worldbook_bulk_update_payload,
    _build_worldbook_create_payload,
    _build_worldbook_delete_payload,
    _build_worldbook_duplicate_payload,
    _build_worldbook_update_payload,
)
from app.api.routes.worldbook_route_preview import (
    _build_worldbook_auto_update_payload,
    _build_worldbook_preview_payload,
)
from app.core.errors import ok_payload
from app.schemas.worldbook import (
    WorldBookBulkDeleteRequest,
    WorldBookBulkUpdateRequest,
    WorldBookDuplicateRequest,
    WorldBookEntryCreate,
    WorldBookEntryUpdate,
    WorldBookImportAllRequest,
    WorldBookPreviewTriggerRequest,
)

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
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_auto_update_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            chapter_id=chapter_id,
        ),
    )


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
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookEntryCreate,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_create_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            body=body,
        ),
    )


@router.put('/worldbook_entries/{entry_id}')
def update_worldbook_entry(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    entry_id: str,
    body: WorldBookEntryUpdate,
) -> dict:
    request_id = request.state.request_id
    row = require_worldbook_entry_editor(db, entry_id=entry_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_update_payload(
            db,
            row=row,
            actor_user_id=user_id,
            request_id=request_id,
            body=body,
        ),
    )


@router.delete('/worldbook_entries/{entry_id}')
def delete_worldbook_entry(request: Request, db: DbDep, user_id: UserIdDep, entry_id: str) -> dict:
    request_id = request.state.request_id
    row = require_worldbook_entry_editor(db, entry_id=entry_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_worldbook_delete_payload(
            db,
            row=row,
            actor_user_id=user_id,
            request_id=request_id,
        ),
    )


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
    return ok_payload(request_id=request_id, data=_build_worldbook_preview_payload(db, project_id=project_id, body=body))
