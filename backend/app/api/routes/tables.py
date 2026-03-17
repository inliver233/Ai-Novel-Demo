from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.api.routes.table_route_helpers import (
    _build_project_table_payload,
    _build_project_table_rows_payload,
    _build_project_tables_payload,
    _create_project_table_payload,
    _create_project_table_row_payload,
    _delete_project_table_payload,
    _delete_project_table_row_payload,
    _project_has_tables,
    _require_project_table,
    _require_project_table_row,
    _schedule_project_table_ai_update_payload,
    _update_project_table_payload,
    _update_project_table_row_payload,
)
from app.api.routes.table_route_models import (
    TableAiUpdateRequest,
    TableCreateRequest,
    TableRowCreateRequest,
    TableRowUpdateRequest,
    TableUpdateRequest,
)
from app.core.errors import AppError, ok_payload
from app.services.project_seed_service import ensure_default_numeric_tables

router = APIRouter()


@router.get("/projects/{project_id}/tables")
def list_project_tables(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    include_schema: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    seed_defaults = False
    if not _project_has_tables(db, project_id=project_id):
        try:
            require_project_editor(db, project_id=project_id, user_id=user_id)
        except AppError:
            pass
        else:
            seed_defaults = True

    return ok_payload(
        request_id=request_id,
        data=_build_project_tables_payload(
            db,
            project_id=project_id,
            include_schema=include_schema,
            seed_defaults=seed_defaults,
        ),
    )


@router.post("/projects/{project_id}/tables/seed_defaults")
def seed_default_project_tables(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    result = ensure_default_numeric_tables(db, project_id=project_id)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/tables")
def create_project_table(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: TableCreateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_create_project_table_payload(db, project_id=project_id, body=body))


@router.get("/projects/{project_id}/tables/{table_id}")
def get_project_table(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    include_schema: bool = Query(default=True),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    return ok_payload(request_id=request_id, data=_build_project_table_payload(db, table=table, include_schema=include_schema))


@router.put("/projects/{project_id}/tables/{table_id}")
def update_project_table(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    body: TableUpdateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    return ok_payload(request_id=request_id, data=_update_project_table_payload(db, table=table, body=body))


@router.delete("/projects/{project_id}/tables/{table_id}")
def delete_project_table(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    return ok_payload(request_id=request_id, data=_delete_project_table_payload(db, table=table))


@router.get("/projects/{project_id}/tables/{table_id}/rows")
def list_project_table_rows(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    return ok_payload(request_id=request_id, data=_build_project_table_rows_payload(db, table=table, offset=offset, limit=limit))


@router.post("/projects/{project_id}/tables/{table_id}/rows")
def create_project_table_row(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    body: TableRowCreateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    return ok_payload(request_id=request_id, data=_create_project_table_row_payload(db, project_id=project_id, table=table, body=body))


@router.put("/projects/{project_id}/tables/{table_id}/rows/{row_id}")
def update_project_table_row(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    row_id: str,
    body: TableRowUpdateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    row = _require_project_table_row(db, project_id=project_id, table_id=table_id, row_id=row_id)
    return ok_payload(request_id=request_id, data=_update_project_table_row_payload(db, table=table, row=row, body=body))


@router.delete("/projects/{project_id}/tables/{table_id}/rows/{row_id}")
def delete_project_table_row(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    row_id: str,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    _require_project_table(db, project_id=project_id, table_id=table_id)
    row = _require_project_table_row(db, project_id=project_id, table_id=table_id, row_id=row_id)
    return ok_payload(request_id=request_id, data=_delete_project_table_row_payload(db, row=row))


@router.post("/projects/{project_id}/tables/{table_id}/ai_update")
def schedule_project_table_ai_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    table_id: str,
    body: TableAiUpdateRequest,
    chapter_id: str | None = Query(default=None, max_length=36),
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    table = _require_project_table(db, project_id=project_id, table_id=table_id)
    return ok_payload(
        request_id=request_id,
        data=_schedule_project_table_ai_update_payload(
            db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            table=table,
            focus=body.focus,
            chapter_id=chapter_id,
        ),
    )
