from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import DbDep, UserIdDep, require_owned_project
from app.core.errors import ok_payload
from app.models.project_settings import ProjectSettings
from app.schemas.settings import ProjectSettingsOut, ProjectSettingsUpdate

router = APIRouter()


@router.get("/projects/{project_id}/settings")
def get_settings(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id, world_setting="", style_guide="", constraints="")
        db.add(row)
        db.commit()
        db.refresh(row)

    payload = ProjectSettingsOut(
        project_id=row.project_id,
        world_setting=row.world_setting or "",
        style_guide=row.style_guide or "",
        constraints=row.constraints or "",
    ).model_dump()
    return ok_payload(request_id=request_id, data={"settings": payload})


@router.put("/projects/{project_id}/settings")
def put_settings(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: ProjectSettingsUpdate) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id, world_setting="", style_guide="", constraints="")
        db.add(row)

    if body.world_setting is not None:
        row.world_setting = body.world_setting
    if body.style_guide is not None:
        row.style_guide = body.style_guide
    if body.constraints is not None:
        row.constraints = body.constraints

    db.commit()
    db.refresh(row)
    payload = ProjectSettingsOut(
        project_id=row.project_id,
        world_setting=row.world_setting or "",
        style_guide=row.style_guide or "",
        constraints=row.constraints or "",
    ).model_dump()
    return ok_payload(request_id=request_id, data={"settings": payload})

