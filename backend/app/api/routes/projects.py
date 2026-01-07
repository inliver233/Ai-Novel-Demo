from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import case, func, select

from app.api.deps import DbDep, UserIdDep, require_owned_llm_profile, require_owned_outline, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.llm.utils import default_max_tokens, is_default_like_max_tokens, normalize_base_url
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.llm_profile import LLMProfile
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.prompt_presets import ensure_default_chapter_preset, ensure_default_outline_preset

router = APIRouter()

PROJECTS_SUMMARY_OUTLINE_MAX_CHARS = 2048


@router.get("/projects")
def list_projects(request: Request, db: DbDep, user_id: UserIdDep) -> dict:
    request_id = request.state.request_id
    projects = (
        db.execute(select(Project).where(Project.owner_user_id == user_id).order_by(Project.created_at.desc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"projects": [ProjectOut.model_validate(p).model_dump() for p in projects]})


@router.get("/projects/summary")
def list_projects_summary(request: Request, db: DbDep, user_id: UserIdDep) -> dict:
    request_id = request.state.request_id
    projects = (
        db.execute(select(Project).where(Project.owner_user_id == user_id).order_by(Project.created_at.desc()))
        .scalars()
        .all()
    )
    if not projects:
        return ok_payload(request_id=request_id, data={"items": []})

    project_ids = [p.id for p in projects]

    settings_rows = (
        db.execute(select(ProjectSettings).where(ProjectSettings.project_id.in_(project_ids)))
        .scalars()
        .all()
    )
    settings_by_project_id = {r.project_id: r for r in settings_rows}

    character_count_rows = (
        db.execute(
            select(Character.project_id, func.count(Character.id))
            .where(Character.project_id.in_(project_ids))
            .group_by(Character.project_id)
        )
        .all()
    )
    character_count_by_project_id = {str(project_id): int(count or 0) for project_id, count in character_count_rows}

    active_outline_ids = [p.active_outline_id for p in projects if p.active_outline_id]
    outline_by_id: dict[str, Outline] = {}
    if active_outline_ids:
        outlines = db.execute(select(Outline).where(Outline.id.in_(active_outline_ids))).scalars().all()
        outline_by_id = {o.id: o for o in outlines}

    chapter_stats_rows = (
        db.execute(
            select(
                Chapter.project_id,
                func.count(Chapter.id),
                func.sum(case((Chapter.status == "done", 1), else_=0)),
            )
            .where(Chapter.project_id.in_(project_ids))
            .group_by(Chapter.project_id)
        )
        .all()
    )
    chapter_stats_by_project_id: dict[str, tuple[int, int]] = {
        str(project_id): (int(total or 0), int(done or 0)) for project_id, total, done in chapter_stats_rows
    }

    presets = db.execute(select(LLMPreset).where(LLMPreset.project_id.in_(project_ids))).scalars().all()
    preset_by_project_id = {p.project_id: p for p in presets}

    profile_ids = sorted({p.llm_profile_id for p in projects if p.llm_profile_id})
    profile_has_key_by_id: dict[str, bool] = {}
    if profile_ids:
        profile_rows = (
            db.execute(
                select(LLMProfile.id, LLMProfile.api_key_ciphertext)
                .where(LLMProfile.owner_user_id == user_id, LLMProfile.id.in_(profile_ids))
                .order_by(LLMProfile.updated_at.desc())
            )
            .all()
        )
        profile_has_key_by_id = {str(pid): bool(ciphertext) for pid, ciphertext in profile_rows}

    items: list[dict] = []
    for project in projects:
        settings = settings_by_project_id.get(project.id)
        characters_count = int(character_count_by_project_id.get(project.id, 0))

        outline_content_md = ""
        outline_content_len = 0
        outline_content_truncated = False
        if project.active_outline_id:
            outline = outline_by_id.get(project.active_outline_id)
            full_outline = (outline.content_md or "") if outline is not None else ""
            outline_content_len = len(full_outline)
            outline_content_truncated = outline_content_len > PROJECTS_SUMMARY_OUTLINE_MAX_CHARS
            outline_content_md = full_outline[:PROJECTS_SUMMARY_OUTLINE_MAX_CHARS] if outline_content_truncated else full_outline

        chapters_total, chapters_done = chapter_stats_by_project_id.get(project.id, (0, 0))

        preset = preset_by_project_id.get(project.id)
        llm_preset_out = None
        if preset is not None:
            llm_preset_out = {"provider": preset.provider, "model": preset.model}

        llm_profile_has_api_key = False
        if project.llm_profile_id:
            llm_profile_has_api_key = bool(profile_has_key_by_id.get(project.llm_profile_id, False))

        settings_out = None
        if settings is not None:
            settings_out = {
                "project_id": settings.project_id,
                "world_setting": settings.world_setting or "",
                "style_guide": settings.style_guide or "",
                "constraints": settings.constraints or "",
            }

        items.append(
            {
                "project": ProjectOut.model_validate(project).model_dump(),
                "settings": settings_out,
                "characters_count": characters_count,
                "outline_content_md": outline_content_md,
                "outline_content_len": outline_content_len,
                "outline_content_truncated": outline_content_truncated,
                "chapters_total": chapters_total,
                "chapters_done": chapters_done,
                "llm_preset": llm_preset_out,
                "llm_profile_has_api_key": llm_profile_has_api_key,
            }
        )

    return ok_payload(request_id=request_id, data={"items": items})


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
                    max_tokens=default_max_tokens(profile.provider, profile.model),
                    presence_penalty=0.0,
                    frequency_penalty=0.0,
                    top_k=None,
                    stop_json="[]",
                    timeout_seconds=90,
                    extra_json="{}",
                )
                db.add(preset)

            old_provider = preset.provider
            preset.provider = profile.provider
            preset.model = profile.model
            if is_default_like_max_tokens(old_provider, preset.max_tokens):
                preset.max_tokens = default_max_tokens(profile.provider, profile.model)
            if profile.provider in ("openai", "openai_responses"):
                preset.base_url = normalize_base_url(profile.base_url or "https://api.openai.com/v1")
            elif profile.provider in ("openai_compatible", "openai_responses_compatible"):
                if not profile.base_url:
                    raise AppError(code="LLM_CONFIG_ERROR", message=f"{profile.provider} 配置必须填写 base_url", status_code=400)
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
