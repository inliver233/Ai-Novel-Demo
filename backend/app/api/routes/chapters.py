from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, UserIdDep, require_owned_chapter, require_owned_outline, require_owned_project
from app.core.errors import AppError, ok_payload
from app.core.logging import log_event
from app.db.session import SessionLocal
from app.db.utils import new_id
from app.llm.client import call_llm_stream
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.schemas.chapters import BulkCreateRequest, ChapterCreate, ChapterOut, ChapterUpdate
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.services.generation_service import call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.length_control import estimate_max_tokens
from app.services.output_parsers import parse_chapter_output
from app.services.outline_store import ensure_active_outline
from app.services.prompt_store import ensure_prompt_templates, format_characters
from app.services.prompting import render_template
from app.services.run_store import write_generation_run
from app.utils.sse_response import (
    create_sse_response,
    sse_chunk,
    sse_done,
    sse_error,
    sse_heartbeat,
    sse_progress,
    sse_result,
)

router = APIRouter()
logger = logging.getLogger("ainovel")


@router.get("/projects/{project_id}/chapters")
def list_chapters(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    outline_id: str | None = Query(default=None),
) -> dict:
    request_id = request.state.request_id
    project = require_owned_project(db, project_id=project_id, user_id=user_id)
    if outline_id:
        outline = require_owned_outline(db, outline_id=outline_id, user_id=user_id)
        if outline.project_id != project_id:
            raise AppError.validation("outline_id 不属于当前项目")
        target_outline_id = outline.id
    else:
        target_outline_id = ensure_active_outline(db, project=project).id

    rows = (
        db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id, Chapter.outline_id == target_outline_id)
            .order_by(Chapter.number.asc())
        )
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"chapters": [ChapterOut.model_validate(r).model_dump() for r in rows]})


@router.post("/projects/{project_id}/chapters")
def create_chapter(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: ChapterCreate,
    outline_id: str | None = Query(default=None),
) -> dict:
    request_id = request.state.request_id
    project = require_owned_project(db, project_id=project_id, user_id=user_id)
    if outline_id:
        outline = require_owned_outline(db, outline_id=outline_id, user_id=user_id)
        if outline.project_id != project_id:
            raise AppError.validation("outline_id 不属于当前项目")
        target_outline_id = outline.id
    else:
        target_outline_id = ensure_active_outline(db, project=project).id
    row = Chapter(
        id=new_id(),
        project_id=project_id,
        outline_id=target_outline_id,
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
    outline_id: str | None = Query(default=None),
) -> dict:
    request_id = request.state.request_id
    project = require_owned_project(db, project_id=project_id, user_id=user_id)
    if outline_id:
        outline = require_owned_outline(db, outline_id=outline_id, user_id=user_id)
        if outline.project_id != project_id:
            raise AppError.validation("outline_id 不属于当前项目")
        target_outline_id = outline.id
    else:
        target_outline_id = ensure_active_outline(db, project=project).id

    has_any = (
        db.execute(select(Chapter.id).where(Chapter.project_id == project_id, Chapter.outline_id == target_outline_id).limit(1)).first()
        is not None
    )
    if has_any and not replace:
        raise AppError.conflict("该大纲已存在章节，无法创建（请选择覆盖创建）")

    numbers = [c.number for c in body.chapters]
    if len(numbers) != len(set(numbers)):
        raise AppError.validation("chapters.number 不能重复")

    if replace:
        db.execute(delete(Chapter).where(Chapter.project_id == project_id, Chapter.outline_id == target_outline_id))
        db.commit()

    created: list[Chapter] = [
        Chapter(
            id=new_id(),
            project_id=project_id,
            outline_id=target_outline_id,
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
    resolved_api_key: str | None = x_llm_api_key

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
        if x_llm_provider and preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)

        if not resolved_api_key:
            raise AppError(code="LLM_KEY_MISSING", message="请先填写 API Key", status_code=401)

        templates = ensure_prompt_templates(db, project_id)
        tpl = templates.get("chapter_generate")
        if tpl is None:
            raise AppError(code="DB_ERROR", message="缺少 chapter_generate 模板", status_code=500)

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

        prev_text = ""
        if body.context.previous_chapter and chapter.number > 1:
            prev = (
                db.execute(
                    select(Chapter).where(
                        Chapter.project_id == project_id,
                        Chapter.outline_id == chapter.outline_id,
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

        requirements_obj: dict[str, object] = {}
        if body.target_word_count is not None:
            requirements_obj["target_word_count"] = body.target_word_count
        requirements_text = json.dumps(requirements_obj, ensure_ascii=False, indent=2) if requirements_obj else ""

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
            "requirements": requirements_text,
            "target_word_count": str(body.target_word_count or ""),
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

    if body.target_word_count is not None:
        llm_call = with_param_overrides(
            llm_call,
            {"max_tokens": estimate_max_tokens(target_word_count=body.target_word_count, provider=llm_call.provider)},
        )

    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="chapter",
        api_key=str(resolved_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        llm_call=llm_call,
    )

    data, warnings, parse_error = parse_chapter_output(llm_result.text, finish_reason=llm_result.finish_reason)
    if warnings:
        data["warnings"] = warnings
    if parse_error is not None:
        data["parse_error"] = parse_error
    return ok_payload(request_id=request_id, data=data)


@router.post("/chapters/{chapter_id}/generate-stream")
def generate_chapter_stream(
    request: Request,
    chapter_id: str,
    body: ChapterGenerateRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key"),
):
    request_id = request.state.request_id

    def event_generator():
        yield sse_progress(message="准备生成...", progress=0)

        prompt_system = ""
        prompt_user = ""
        llm_call = None
        project_id = ""
        resolved_api_key: str | None = x_llm_api_key

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

            if not resolved_api_key:
                raise AppError(code="LLM_KEY_MISSING", message="请先填写 API Key", status_code=401)

            templates = ensure_prompt_templates(db, project_id)
            tpl = templates.get("chapter_generate")
            if tpl is None:
                raise AppError(code="DB_ERROR", message="缺少 chapter_generate 模板", status_code=500)

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

            prev_text = ""
            if body.context.previous_chapter and chapter.number > 1:
                prev = (
                    db.execute(
                        select(Chapter).where(
                            Chapter.project_id == project_id,
                            Chapter.outline_id == chapter.outline_id,
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

            requirements_obj: dict[str, object] = {}
            if body.target_word_count is not None:
                requirements_obj["target_word_count"] = body.target_word_count
            requirements_text = json.dumps(requirements_obj, ensure_ascii=False, indent=2) if requirements_obj else ""

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
                "requirements": requirements_text,
                "target_word_count": str(body.target_word_count or ""),
                "instruction": instruction,
                "previous_chapter": prev_text,
            }

            prompt_system, _ = render_template(tpl.system_template or "", values)
            prompt_user, _ = render_template(tpl.user_template or "", values)

            llm_call = prepare_llm_call(preset)
        except GeneratorExit:
            return
        except AppError as exc:
            yield sse_error(error=f"{exc.message} ({exc.code})", code=exc.status_code)
            yield sse_done()
            return
        finally:
            db.close()

        if llm_call is None:
            yield sse_error(error="LLM 调用准备失败", code=500)
            yield sse_done()
            return

        if body.target_word_count is not None:
            llm_call = with_param_overrides(
                llm_call,
                {"max_tokens": estimate_max_tokens(target_word_count=body.target_word_count, provider=llm_call.provider)},
            )

        yield sse_progress(message="调用模型...", progress=10)

        raw_output = ""
        finish_reason: str | None = None
        dropped_params: list[str] = []
        latency_ms: int | None = None
        stream_run_written = False
        try:
            if llm_call.provider in ("openai", "openai_compatible"):
                stream_iter, state = call_llm_stream(
                    provider=llm_call.provider,
                    base_url=llm_call.base_url,
                    model=llm_call.model,
                    api_key=str(resolved_api_key),
                    system=prompt_system,
                    user=prompt_user,
                    params=llm_call.params,
                    timeout_seconds=llm_call.timeout_seconds,
                    extra=llm_call.extra,
                )

                last_progress = 10
                last_progress_ts = 0.0
                chunk_count = 0
                target = body.target_word_count or 0
                try:
                    for delta in stream_iter:
                        raw_output += delta
                        yield sse_chunk(delta)
                        chunk_count += 1
                        if chunk_count % 12 == 0:
                            yield sse_heartbeat()
                        now = time.monotonic()
                        if now - last_progress_ts >= 0.8:
                            if target > 0:
                                next_progress = 10 + int(min(1.0, len(raw_output) / float(target)) * 80)
                            else:
                                next_progress = 10 + int(min(1.0, len(raw_output) / 12000.0) * 80)
                            next_progress = max(last_progress, min(90, next_progress))
                            if next_progress != last_progress:
                                last_progress = next_progress
                                yield sse_progress(message="生成中...", progress=next_progress, word_count=len(raw_output))
                            last_progress_ts = now
                finally:
                    close = getattr(stream_iter, "close", None)
                    if callable(close):
                        close()

                finish_reason = state.finish_reason
                dropped_params = state.dropped_params
                latency_ms = state.latency_ms

                log_event(
                    logger,
                    "info",
                    llm={
                        "provider": llm_call.provider,
                        "model": llm_call.model,
                        "timeout_seconds": llm_call.timeout_seconds,
                        "prompt_chars": len(prompt_system) + len(prompt_user),
                        "output_chars": len(raw_output or ""),
                        "dropped_params": dropped_params,
                        "finish_reason": finish_reason,
                        "stream": True,
                    },
                )
                write_generation_run(
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    run_type="chapter_stream",
                    provider=llm_call.provider,
                    model=llm_call.model,
                    prompt_system=prompt_system,
                    prompt_user=prompt_user,
                    params_json=llm_call.params_json,
                    output_text=raw_output,
                    error_json=None,
                )
                stream_run_written = True
            else:
                fallback = call_llm_and_record(
                    logger=logger,
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    run_type="chapter_stream",
                    api_key=str(resolved_api_key),
                    prompt_system=prompt_system,
                    prompt_user=prompt_user,
                    llm_call=llm_call,
                )
                raw_output = fallback.text
                finish_reason = fallback.finish_reason
                dropped_params = fallback.dropped_params
                latency_ms = fallback.latency_ms

            yield sse_progress(message="解析输出...", progress=90)
            data, warnings, parse_error = parse_chapter_output(raw_output, finish_reason=finish_reason)
            if warnings:
                data["warnings"] = warnings
            if parse_error is not None:
                data["parse_error"] = parse_error
            if finish_reason is not None:
                data["finish_reason"] = finish_reason
            if latency_ms is not None:
                data["latency_ms"] = latency_ms
            if dropped_params:
                data["dropped_params"] = dropped_params

            yield sse_progress(message="完成", progress=100, status="success")
            yield sse_result(data)
            yield sse_done()
        except GeneratorExit:
            return
        except AppError as exc:
            if (
                llm_call is not None
                and llm_call.provider in ("openai", "openai_compatible")
                and not stream_run_written
            ):
                write_generation_run(
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    run_type="chapter_stream",
                    provider=llm_call.provider,
                    model=llm_call.model,
                    prompt_system=prompt_system,
                    prompt_user=prompt_user,
                    params_json=llm_call.params_json,
                    output_text=raw_output or None,
                    error_json=json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False),
                )
            yield sse_error(error=f"{exc.message} ({exc.code})", code=exc.status_code)
            yield sse_done()
        except Exception:
            yield sse_error(error="服务器内部错误", code=500)
            yield sse_done()

    return create_sse_response(event_generator())
