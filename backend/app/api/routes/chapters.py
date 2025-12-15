from __future__ import annotations
import logging

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, UserIdDep, require_owned_chapter, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.schemas.chapters import BulkCreateRequest, ChapterCreate, ChapterOut, ChapterUpdate
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.services.generation_service import call_llm_and_record, prepare_llm_call
from app.services.prompt_store import ensure_prompt_templates, format_characters
from app.services.prompting import extract_json_object, render_template

router = APIRouter()
logger = logging.getLogger("ainovel")


@router.get("/projects/{project_id}/chapters")
def list_chapters(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    rows = db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.number.asc())).scalars().all()
    return ok_payload(request_id=request_id, data={"chapters": [ChapterOut.model_validate(r).model_dump() for r in rows]})


@router.post("/projects/{project_id}/chapters")
def create_chapter(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: ChapterCreate) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    row = Chapter(
        id=new_id(),
        project_id=project_id,
        number=body.number,
        title=body.title,
        plan=body.plan,
        status=body.status,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict("章节号已存在", details={"field": "number"})
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"chapter": ChapterOut.model_validate(row).model_dump()})


@router.post("/projects/{project_id}/chapters/bulk_create")
def bulk_create(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: BulkCreateRequest,
    replace: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    has_any = db.execute(select(Chapter.id).where(Chapter.project_id == project_id).limit(1)).first() is not None
    if has_any and not replace:
        raise AppError.conflict("项目已存在章节，无法创建（请选择覆盖创建）")

    numbers = [c.number for c in body.chapters]
    if len(numbers) != len(set(numbers)):
        raise AppError.validation("chapters.number 不能重复")

    if replace:
        db.execute(delete(Chapter).where(Chapter.project_id == project_id))
        db.commit()

    created: list[Chapter] = [
        Chapter(
            id=new_id(),
            project_id=project_id,
            number=c.number,
            title=c.title,
            plan=c.plan,
            status="planned",
        )
        for c in body.chapters
    ]
    db.add_all(created)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict("章节创建冲突（请检查章节号）")

    created_sorted = sorted(created, key=lambda x: x.number)
    return ok_payload(
        request_id=request_id,
        data={"chapters": [ChapterOut.model_validate(r).model_dump() for r in created_sorted]},
    )


@router.get("/chapters/{chapter_id}")
def get_chapter(request: Request, db: DbDep, user_id: UserIdDep, chapter_id: str) -> dict:
    request_id = request.state.request_id
    row = require_owned_chapter(db, chapter_id=chapter_id, user_id=user_id)
    return ok_payload(request_id=request_id, data={"chapter": ChapterOut.model_validate(row).model_dump()})


@router.put("/chapters/{chapter_id}")
def update_chapter(request: Request, db: DbDep, user_id: UserIdDep, chapter_id: str, body: ChapterUpdate) -> dict:
    request_id = request.state.request_id
    row = require_owned_chapter(db, chapter_id=chapter_id, user_id=user_id)

    if body.title is not None:
        row.title = body.title
    if body.plan is not None:
        row.plan = body.plan
    if body.content_md is not None:
        row.content_md = body.content_md
    if body.summary is not None:
        row.summary = body.summary
    if body.status is not None:
        row.status = body.status

    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"chapter": ChapterOut.model_validate(row).model_dump()})


@router.delete("/chapters/{chapter_id}")
def delete_chapter(request: Request, db: DbDep, user_id: UserIdDep, chapter_id: str) -> dict:
    request_id = request.state.request_id
    row = require_owned_chapter(db, chapter_id=chapter_id, user_id=user_id)
    db.delete(row)
    db.commit()
    return ok_payload(request_id=request_id, data={})


@router.post("/chapters/{chapter_id}/generate")
def generate_chapter(
    request: Request,
    chapter_id: str,
    body: ChapterGenerateRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key"),
) -> dict:
    request_id = request.state.request_id
    if not x_llm_provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="缺少 X-LLM-Provider", status_code=400)
    if not x_llm_api_key:
        raise AppError(code="LLM_KEY_MISSING", message="请先填写 API Key", status_code=401)

    prompt_system = ""
    prompt_user = ""
    llm_call = None
    project_id = ""

    db = SessionLocal()
    try:
        chapter = require_owned_chapter(db, chapter_id=chapter_id, user_id=user_id)
        project_id = chapter.project_id
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        preset = db.get(LLMPreset, project_id)
        if preset is None:
            raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
        if preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)

        templates = ensure_prompt_templates(db, project_id)
        tpl = templates.get("chapter_generate")
        if tpl is None:
            raise AppError(code="DB_ERROR", message="缺少 chapter_generate 模板", status_code=500)

        settings_row = db.get(ProjectSettings, project_id)
        outline_row = db.get(Outline, project_id)

        world_setting = (settings_row.world_setting if settings_row else "") or ""
        style_guide = (settings_row.style_guide if settings_row else "") or ""
        constraints = (settings_row.constraints if settings_row else "") or ""

        if not body.context.include_world_setting:
            world_setting = ""
        if not body.context.include_style_guide:
            style_guide = ""
        if not body.context.include_constraints:
            constraints = ""

        outline_text = (outline_row.content_md if outline_row else "") or ""
        if not body.context.include_outline:
            outline_text = ""

        chars: list[Character] = []
        if body.context.character_ids:
            chars = (
                db.execute(
                    select(Character).where(
                        Character.project_id == project_id,
                        Character.id.in_(body.context.character_ids),
                    )
                )
                .scalars()
                .all()
            )
        characters_text = format_characters(chars)

        prev_text = ""
        if body.context.previous_chapter and chapter.number > 1:
            prev = (
                db.execute(
                    select(Chapter).where(
                        Chapter.project_id == project_id,
                        Chapter.number == (chapter.number - 1),
                    )
                )
                .scalars()
                .first()
            )
            if prev is not None:
                if body.context.previous_chapter == "summary":
                    prev_text = (prev.summary or "").strip()
                elif body.context.previous_chapter == "content":
                    prev_text = (prev.content_md or "").strip()

        instruction = body.instruction.strip()
        if body.mode == "append":
            instruction = "【追加模式】只输出需要追加到正文末尾的新增片段，不要重复已写内容。\\n" + instruction
        else:
            instruction = "【替换模式】输出完整替换稿（整章）。\\n" + instruction

        values = {
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": outline_text,
            "chapter_number": str(chapter.number),
            "chapter_title": (chapter.title or ""),
            "chapter_plan": (chapter.plan or ""),
            "requirements": "",
            "instruction": instruction,
            "previous_chapter": prev_text,
        }

        prompt_system, _ = render_template(tpl.system_template or "", values)
        prompt_user, _ = render_template(tpl.user_template or "", values)

        llm_call = prepare_llm_call(preset)
    finally:
        db.close()

    if llm_call is None:
        raise AppError(code="INTERNAL_ERROR", message="LLM 调用准备失败", status_code=500)

    raw_output = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="chapter",
        api_key=str(x_llm_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        llm_call=llm_call,
    )

    parsed, _ = extract_json_object(raw_output)
    content_md = raw_output
    summary = ""
    if isinstance(parsed, dict):
        content_md = str(parsed.get("content_md") or raw_output)
        summary = str(parsed.get("summary") or "")

    return ok_payload(request_id=request_id, data={"content_md": content_md, "summary": summary, "raw_output": raw_output})
