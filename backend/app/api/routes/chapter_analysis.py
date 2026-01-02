from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.api.deps import UserIdDep, require_owned_chapter
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.models.character import Character
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.schemas.chapter_analysis import ChapterAnalyzeRequest, ChapterRewriteRequest
from app.services.generation_service import call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.output_contracts import contract_for_task
from app.services.prompt_presets import (
    ensure_default_chapter_analyze_preset,
    ensure_default_chapter_rewrite_preset,
    render_preset_for_task,
)
from app.services.prompt_store import format_characters

from app.services.chapter_context_service import build_smart_context

router = APIRouter()
logger = logging.getLogger("ainovel")


@router.post("/chapters/{chapter_id}/analyze")
def analyze_chapter(
    request: Request,
    chapter_id: str,
    body: ChapterAnalyzeRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key"),
) -> dict:
    request_id = request.state.request_id
    resolved_api_key = ""

    prompt_system = ""
    prompt_user = ""
    prompt_render_log_json: str | None = None
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
        if x_llm_provider and preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)
        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=x_llm_api_key)

        ensure_default_chapter_analyze_preset(db, project_id=project_id, activate=True)

        settings_row = db.get(ProjectSettings, project_id)
        outline_row = db.get(Outline, chapter.outline_id)

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

        smart_recent_summaries = ""
        smart_recent_full = ""
        smart_story_skeleton = ""
        if body.context.include_smart_context:
            smart_recent_summaries, smart_recent_full, smart_story_skeleton = build_smart_context(
                db,
                project_id=project_id,
                outline_id=chapter.outline_id,
                chapter_number=int(chapter.number),
            )

        draft_title = body.draft_title if body.draft_title is not None else (chapter.title or "")
        draft_plan = body.draft_plan if body.draft_plan is not None else (chapter.plan or "")
        draft_summary = body.draft_summary if body.draft_summary is not None else (chapter.summary or "")
        draft_content_md = body.draft_content_md if body.draft_content_md is not None else (chapter.content_md or "")

        values: dict[str, object] = {
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": outline_text,
            "chapter_number": str(chapter.number),
            "chapter_title": draft_title,
            "chapter_plan": draft_plan,
            "chapter_summary": draft_summary,
            "chapter_content_md": draft_content_md,
            "instruction": body.instruction.strip(),
            "smart_context_recent_summaries": smart_recent_summaries,
            "smart_context_recent_full": smart_recent_full,
            "smart_context_story_skeleton": smart_story_skeleton,
        }
        values["project"] = {
            "name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
        }
        values["story"] = {
            "outline": outline_text,
            "chapter_number": int(chapter.number),
            "chapter_title": draft_title,
            "chapter_plan": draft_plan,
            "chapter_summary": draft_summary,
            "chapter_content_md": draft_content_md,
            "smart_context_recent_summaries": smart_recent_summaries,
            "smart_context_recent_full": smart_recent_full,
            "smart_context_story_skeleton": smart_story_skeleton,
        }
        values["user"] = {"instruction": body.instruction.strip()}

        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="chapter_analyze",
            values=values,  # type: ignore[arg-type]
            macro_seed=f"{request_id}:analyze",
            provider=preset.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)
        llm_call = prepare_llm_call(preset)
    finally:
        db.close()

    if llm_call is None:
        raise AppError(code="INTERNAL_ERROR", message="LLM 调用准备失败", status_code=500)
    if not prompt_system.strip() and not prompt_user.strip():
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 chapter_analyze 提示词预设/提示块", status_code=400)

    llm_call = with_param_overrides(llm_call, {"temperature": 0.2, "max_tokens": 2048})
    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="chapter_analyze",
        api_key=str(resolved_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
        llm_call=llm_call,
    )

    contract = contract_for_task("chapter_analyze")
    parsed = contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
    data, warnings, parse_error = parsed.data, parsed.warnings, parsed.parse_error
    data["generation_run_id"] = llm_result.run_id
    if warnings:
        data["warnings"] = warnings
    if parse_error is not None:
        data["parse_error"] = parse_error
    if llm_result.finish_reason is not None:
        data["finish_reason"] = llm_result.finish_reason
    return ok_payload(request_id=request_id, data=data)


@router.post("/chapters/{chapter_id}/rewrite")
def rewrite_chapter(
    request: Request,
    chapter_id: str,
    body: ChapterRewriteRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key"),
) -> dict:
    request_id = request.state.request_id
    resolved_api_key = ""

    prompt_system = ""
    prompt_user = ""
    prompt_render_log_json: str | None = None
    llm_call = None
    project_id = ""

    if not body.analysis:
        raise AppError.validation(message="analysis 不能为空，请先完成章节分析")

    analysis_json = json.dumps(body.analysis, ensure_ascii=False, indent=2)

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
        if x_llm_provider and preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)
        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=x_llm_api_key)

        ensure_default_chapter_rewrite_preset(db, project_id=project_id, activate=True)

        settings_row = db.get(ProjectSettings, project_id)
        outline_row = db.get(Outline, chapter.outline_id)

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

        smart_recent_summaries = ""
        smart_recent_full = ""
        smart_story_skeleton = ""
        if body.context.include_smart_context:
            smart_recent_summaries, smart_recent_full, smart_story_skeleton = build_smart_context(
                db,
                project_id=project_id,
                outline_id=chapter.outline_id,
                chapter_number=int(chapter.number),
            )

        draft_title = chapter.title or ""
        draft_plan = chapter.plan or ""
        draft_content_md = body.draft_content_md if body.draft_content_md is not None else (chapter.content_md or "")
        if not draft_content_md.strip():
            raise AppError.validation(message="当前章节正文为空，无法重写")

        values: dict[str, object] = {
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": outline_text,
            "chapter_number": str(chapter.number),
            "chapter_title": draft_title,
            "chapter_plan": draft_plan,
            "chapter_content_md": draft_content_md,
            "analysis_json": analysis_json,
            "instruction": body.instruction.strip(),
            "smart_context_recent_summaries": smart_recent_summaries,
            "smart_context_recent_full": smart_recent_full,
            "smart_context_story_skeleton": smart_story_skeleton,
        }
        values["project"] = {
            "name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
        }
        values["story"] = {
            "outline": outline_text,
            "chapter_number": int(chapter.number),
            "chapter_title": draft_title,
            "chapter_plan": draft_plan,
            "chapter_content_md": draft_content_md,
            "analysis_json": analysis_json,
            "smart_context_recent_summaries": smart_recent_summaries,
            "smart_context_recent_full": smart_recent_full,
            "smart_context_story_skeleton": smart_story_skeleton,
        }
        values["user"] = {"instruction": body.instruction.strip()}

        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="chapter_rewrite",
            values=values,  # type: ignore[arg-type]
            macro_seed=f"{request_id}:rewrite",
            provider=preset.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)
        llm_call = prepare_llm_call(preset)
    finally:
        db.close()

    if llm_call is None:
        raise AppError(code="INTERNAL_ERROR", message="LLM 调用准备失败", status_code=500)
    if not prompt_system.strip() and not prompt_user.strip():
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 chapter_rewrite 提示词预设/提示块", status_code=400)

    llm_call = with_param_overrides(llm_call, {"temperature": 0.35, "max_tokens": 8192})
    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="chapter_rewrite",
        api_key=str(resolved_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
        llm_call=llm_call,
    )

    contract = contract_for_task("chapter_rewrite")
    parsed = contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
    data, warnings, parse_error = parsed.data, parsed.warnings, parsed.parse_error
    data["generation_run_id"] = llm_result.run_id
    if warnings:
        data["warnings"] = warnings
    if parse_error is not None:
        data["parse_error"] = parse_error
    if llm_result.finish_reason is not None:
        data["finish_reason"] = llm_result.finish_reason
    return ok_payload(request_id=request_id, data=data)
