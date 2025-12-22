from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_owned_llm_profile, require_owned_outline, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.llm.utils import normalize_base_url
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.prompt_presets import ensure_default_chapter_preset, ensure_default_outline_preset

router = APIRouter()


@router.get("/projects")
def list_projects(request: Request, db: DbDep, user_id: UserIdDep) -> dict:
    request_id = request.state.request_id
    projects = (
        db.execute(select(Project).where(Project.owner_user_id == user_id).order_by(Project.created_at.desc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"projects": [ProjectOut.model_validate(p).model_dump() for p in projects]})


@router.post("/projects")
def create_project(request: Request, db: DbDep, user_id: UserIdDep, body: ProjectCreate) -> dict:
    request_id = request.state.request_id
    project = Project(
        id=new_id(),
        owner_user_id=user_id,
        name=body.name,
        genre=body.genre,
        logline=body.logline,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # New projects should default to the recommended Prompt Engine presets.
    ensure_default_outline_preset(db, project_id=project.id, activate=True)
    ensure_default_chapter_preset(db, project_id=project.id, activate=True)

    return ok_payload(request_id=request_id, data={"project": ProjectOut.model_validate(project).model_dump()})


@router.get("/projects/{project_id}")
def get_project(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise AppError.not_found()
    return ok_payload(request_id=request_id, data={"project": ProjectOut.model_validate(project).model_dump()})


@router.put("/projects/{project_id}")
def update_project(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: ProjectUpdate) -> dict:
    request_id = request.state.request_id
    project = require_owned_project(db, project_id=project_id, user_id=user_id)

    if body.name is not None:
        project.name = body.name
    if body.genre is not None:
        project.genre = body.genre
    if body.logline is not None:
        project.logline = body.logline

    if "active_outline_id" in body.model_fields_set:
        if body.active_outline_id is None:
            project.active_outline_id = None
        else:
            outline = require_owned_outline(db, outline_id=body.active_outline_id, user_id=user_id)
            if outline.project_id != project_id:
                raise AppError.validation("active_outline_id 不属于当前项目")
            project.active_outline_id = outline.id

    if "llm_profile_id" in body.model_fields_set:
        if body.llm_profile_id is None:
            project.llm_profile_id = None
        else:
            profile = require_owned_llm_profile(db, profile_id=body.llm_profile_id, user_id=user_id)
            project.llm_profile_id = profile.id

            preset = db.get(LLMPreset, project_id)
            if preset is None:
                preset = LLMPreset(
                    project_id=project_id,
                    provider=profile.provider,
                    base_url=None,
                    model=profile.model,
                    temperature=0.7,
                    top_p=1.0,
                    max_tokens=32000,
                    presence_penalty=0.0,
                    frequency_penalty=0.0,
                    top_k=None,
                    stop_json="[]",
                    timeout_seconds=90,
                    extra_json="{}",
                )
                db.add(preset)

            preset.provider = profile.provider
            preset.model = profile.model
            if profile.provider == "openai":
                preset.base_url = normalize_base_url(profile.base_url or "https://api.openai.com/v1")
            elif profile.provider == "openai_compatible":
                if not profile.base_url:
                    raise AppError(code="LLM_CONFIG_ERROR", message="openai_compatible 配置必须填写 base_url", status_code=400)
                preset.base_url = normalize_base_url(profile.base_url)
            elif profile.provider == "anthropic":
                preset.base_url = normalize_base_url(profile.base_url or "https://api.anthropic.com")
            elif profile.provider == "gemini":
                preset.base_url = normalize_base_url(profile.base_url or "https://generativelanguage.googleapis.com")

    db.commit()
    db.refresh(project)
    return ok_payload(request_id=request_id, data={"project": ProjectOut.model_validate(project).model_dump()})


@router.delete("/projects/{project_id}")
def delete_project(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise AppError.not_found()
    db.delete(project)
    db.commit()
    return ok_payload(request_id=request_id, data={})
