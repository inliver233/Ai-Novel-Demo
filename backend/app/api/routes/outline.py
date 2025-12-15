from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.models.character import Character
from app.models.llm_preset import LLMPreset
from app.models.project_settings import ProjectSettings
from app.schemas.outline_generate import OutlineGenerateRequest
from app.services.generation_service import call_llm_and_record, prepare_llm_call
from app.services.prompting import extract_json_object, render_template
from app.services.prompt_store import ensure_prompt_templates, format_characters
from app.models.outline import Outline
from app.schemas.outline import OutlineOut, OutlineUpdate

router = APIRouter()
logger = logging.getLogger("ainovel")


@router.get("/projects/{project_id}/outline")
def get_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    row = db.get(Outline, project_id)
    if row is None:
        row = Outline(project_id=project_id, content_md="")
        db.add(row)
        db.commit()
        db.refresh(row)
    payload = OutlineOut(project_id=row.project_id, content_md=row.content_md or "", updated_at=row.updated_at).model_dump()
    return ok_payload(request_id=request_id, data={"outline": payload})


@router.put("/projects/{project_id}/outline")
def put_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: OutlineUpdate) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    row = db.get(Outline, project_id)
    if row is None:
        row = Outline(project_id=project_id, content_md="")
        db.add(row)

    if body.content_md is not None:
        row.content_md = body.content_md

    db.commit()
    db.refresh(row)
    payload = OutlineOut(project_id=row.project_id, content_md=row.content_md or "", updated_at=row.updated_at).model_dump()
    return ok_payload(request_id=request_id, data={"outline": payload})


@router.post("/projects/{project_id}/outline/generate")
def generate_outline(
    request: Request,
    project_id: str,
    body: OutlineGenerateRequest,
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

    db = SessionLocal()
    try:
        project = require_owned_project(db, project_id=project_id, user_id=user_id)
        preset = db.get(LLMPreset, project_id)
        if preset is None:
            raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
        if preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)

        templates = ensure_prompt_templates(db, project_id)
        tpl = templates.get("outline_generate")
        if tpl is None:
            raise AppError(code="DB_ERROR", message="缺少 outline_generate 模板", status_code=500)

        settings_row = db.get(ProjectSettings, project_id)
        world_setting = (settings_row.world_setting if settings_row else "") or ""
        style_guide = (settings_row.style_guide if settings_row else "") or ""
        constraints = (settings_row.constraints if settings_row else "") or ""
        if not body.context.include_world_setting:
            world_setting = ""
            style_guide = ""
            constraints = ""

        chars: list[Character] = []
        if body.context.include_characters:
            chars = db.execute(select(Character).where(Character.project_id == project_id)).scalars().all()
        characters_text = format_characters(chars)

        requirements_text = json.dumps(body.requirements or {}, ensure_ascii=False, indent=2)

        values = {
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": "",
            "chapter_number": "",
            "chapter_title": "",
            "chapter_plan": "",
            "requirements": requirements_text,
            "instruction": "",
            "previous_chapter": "",
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
        chapter_id=None,
        run_type="outline",
        api_key=str(x_llm_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        llm_call=llm_call,
    )

    parsed, _ = extract_json_object(raw_output)
    outline_md = raw_output
    chapters: list[dict] = []
    parse_error: dict | None = None
    if isinstance(parsed, dict):
        outline_md = str(parsed.get("outline_md") or raw_output)
        parsed_chapters = parsed.get("chapters")
        if isinstance(parsed_chapters, list):
            for item in parsed_chapters:
                if not isinstance(item, dict):
                    continue
                try:
                    number = int(item.get("number"))
                except Exception:
                    continue
                title = str(item.get("title") or "")
                beats_raw = item.get("beats") or []
                beats: list[str] = []
                if isinstance(beats_raw, list):
                    beats = [str(b) for b in beats_raw if b is not None]
                chapters.append({"number": number, "title": title, "beats": beats})

    if not chapters:
        parse_error = {"code": "OUTLINE_PARSE_ERROR", "message": "无法从模型输出解析章节结构"}

    data: dict = {"outline_md": outline_md, "chapters": chapters, "raw_output": raw_output}
    if parse_error is not None:
        data["parse_error"] = parse_error
    return ok_payload(request_id=request_id, data=data)
