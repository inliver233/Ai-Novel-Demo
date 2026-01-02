from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import log_event
from app.db.session import SessionLocal
from app.db.utils import new_id
from app.models.batch_generation_task import BatchGenerationTask, BatchGenerationTaskItem
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.services.chapter_context_service import build_smart_context
from app.services.generation_service import PreparedLlmCall, call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.length_control import estimate_max_tokens
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.output_contracts import contract_for_task
from app.services.prompt_presets import ensure_default_post_edit_preset, ensure_default_plan_preset, render_preset_for_task
from app.services.prompt_store import format_characters

logger = logging.getLogger("ainovel")

PREVIOUS_CHAPTER_ENDING_CHARS = 1000


@dataclass(frozen=True, slots=True)
class BatchGenerateParams:
    instruction: str
    target_word_count: int | None
    plan_first: bool
    post_edit: bool
    include_world_setting: bool
    include_style_guide: bool
    include_constraints: bool
    include_outline: bool
    include_smart_context: bool
    character_ids: list[str]
    previous_chapter: str


def _parse_params(task: BatchGenerationTask) -> BatchGenerateParams:
    raw = {}
    if task.params_json:
        try:
            parsed = json.loads(task.params_json)
            if isinstance(parsed, dict):
                raw = parsed
        except Exception:
            raw = {}

    ctx = raw.get("context")
    ctx_obj = ctx if isinstance(ctx, dict) else {}

    character_ids = ctx_obj.get("character_ids")
    if not isinstance(character_ids, list):
        character_ids = []
    character_ids2 = [str(x) for x in character_ids if x is not None]

    return BatchGenerateParams(
        instruction=str(raw.get("instruction") or "").strip(),
        target_word_count=(int(raw["target_word_count"]) if isinstance(raw.get("target_word_count"), int) else None),
        plan_first=bool(raw.get("plan_first")),
        post_edit=bool(raw.get("post_edit")),
        include_world_setting=bool(ctx_obj.get("include_world_setting", True)),
        include_style_guide=bool(ctx_obj.get("include_style_guide", True)),
        include_constraints=bool(ctx_obj.get("include_constraints", True)),
        include_outline=bool(ctx_obj.get("include_outline", True)),
        include_smart_context=bool(ctx_obj.get("include_smart_context", True)),
        character_ids=character_ids2,
        previous_chapter=str(ctx_obj.get("previous_chapter") or "none"),
    )


def _load_previous_chapter_context_from_db(
    db: Session,
    *,
    project_id: str,
    outline_id: str,
    chapter_number: int,
    previous_chapter: str | None,
) -> tuple[str, str]:
    mode = previous_chapter or "none"
    if mode == "none" or chapter_number <= 1:
        return "", ""

    prev = (
        db.execute(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.outline_id == outline_id,
                Chapter.number == (chapter_number - 1),
            )
        )
        .scalars()
        .first()
    )
    if prev is None:
        return "", ""

    if mode == "summary":
        return (prev.summary or "").strip(), ""
    if mode == "content":
        return (prev.content_md or "").strip(), ""
    if mode == "tail":
        raw = (prev.content_md or "").strip()
        if not raw:
            return "", ""
        tail = raw[-PREVIOUS_CHAPTER_ENDING_CHARS:].lstrip()
        return "", tail

    return "", ""


def _cancel_task(task_id: str) -> None:
    with SessionLocal() as db:
        task = db.get(BatchGenerationTask, task_id)
        if task is None:
            return
        task.status = "canceled"
        items = (
            db.execute(
                select(BatchGenerationTaskItem).where(
                    BatchGenerationTaskItem.task_id == task_id, BatchGenerationTaskItem.status.in_(["queued", "running"])
                )
            )
            .scalars()
            .all()
        )
        for item in items:
            item.status = "canceled"
        db.commit()


def _prepare_project_context(
    *,
    project_id: str,
    outline_id: str,
    actor_user_id: str,
    params: BatchGenerateParams,
) -> tuple[Project, PreparedLlmCall, str, str, str, str, str, str]:
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        preset = db.get(LLMPreset, project_id)
        if preset is None:
            raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)

        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=actor_user_id, header_api_key=None)

        settings_row = db.get(ProjectSettings, project_id)
        outline_row = db.get(Outline, outline_id)

        world_setting = (settings_row.world_setting if settings_row else "") or ""
        style_guide = (settings_row.style_guide if settings_row else "") or ""
        constraints = (settings_row.constraints if settings_row else "") or ""

        if not params.include_world_setting:
            world_setting = ""
        if not params.include_style_guide:
            style_guide = ""
        if not params.include_constraints:
            constraints = ""

        outline_text = (outline_row.content_md if outline_row else "") or ""
        if not params.include_outline:
            outline_text = ""

        chars: list[Character] = []
        if params.character_ids:
            chars = (
                db.execute(
                    select(Character).where(
                        Character.project_id == project_id,
                        Character.id.in_(params.character_ids),
                    )
                )
                .scalars()
                .all()
            )
        characters_text = format_characters(chars)

        llm_call = prepare_llm_call(preset)
        return project, llm_call, resolved_api_key, world_setting, style_guide, constraints, characters_text, outline_text


def run_batch_generation_task(*, task_id: str) -> None:
    """
    Background worker: generate chapters sequentially and persist results as generation_runs + task item status.

    IMPORTANT: Do not write generated content into `chapters` (demo contract: user must click Save).
    """
    with SessionLocal() as db:
        task = db.get(BatchGenerationTask, task_id)
        if task is None:
            return
        if task.status in ("succeeded", "failed", "canceled"):
            return
        if task.cancel_requested:
            task.status = "canceled"
            db.commit()
            return
        task.status = "running"
        db.commit()

        params = _parse_params(task)
        actor_user_id = task.actor_user_id or "local-user"

        rows = db.execute(
            select(BatchGenerationTaskItem.id, BatchGenerationTaskItem.chapter_id, BatchGenerationTaskItem.chapter_number, BatchGenerationTaskItem.status)
            .where(BatchGenerationTaskItem.task_id == task_id)
            .order_by(BatchGenerationTaskItem.chapter_number.asc())
        ).all()

        completed = sum(1 for r in rows if r[3] == "succeeded")
        if completed != int(task.completed_count or 0):
            task.completed_count = int(completed)
            db.commit()

    try:
        project, llm_call_base, resolved_api_key, world_setting, style_guide, constraints, characters_text, outline_text = _prepare_project_context(
            project_id=task.project_id,
            outline_id=task.outline_id,
            actor_user_id=actor_user_id,
            params=params,
        )
    except AppError as exc:
        with SessionLocal() as db:
            task = db.get(BatchGenerationTask, task_id)
            if task is not None:
                task.status = "failed"
                task.error_json = json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False)
                db.commit()
        return

    prev_content_md: str | None = None
    prev_summary: str | None = None

    for item_id, chapter_id, chapter_number, status in rows:
        if status == "succeeded":
            continue

        with SessionLocal() as db:
            task = db.get(BatchGenerationTask, task_id)
            if task is None:
                return
            if task.cancel_requested:
                db.commit()
                _cancel_task(task_id)
                return

            item = db.get(BatchGenerationTaskItem, item_id)
            if item is None:
                task.status = "failed"
                task.error_json = json.dumps({"code": "DB_ERROR", "message": "任务 item 不存在"}, ensure_ascii=False)
                db.commit()
                return
            if item.status == "succeeded":
                continue

            item.status = "running"
            db.commit()

            chapter = db.get(Chapter, chapter_id) if chapter_id else None
            if chapter is None:
                item.status = "failed"
                item.error_message = "章节不存在"
                task.status = "failed"
                task.error_json = json.dumps({"code": "NOT_FOUND", "message": "章节不存在"}, ensure_ascii=False)
                db.commit()
                return

            prev_text = ""
            prev_ending = ""
            mode = params.previous_chapter or "none"
            if prev_content_md is not None or prev_summary is not None:
                if mode == "summary":
                    prev_text = (prev_summary or "").strip()
                elif mode == "content":
                    prev_text = (prev_content_md or "").strip()
                elif mode == "tail":
                    raw_prev = (prev_content_md or "").strip()
                    prev_ending = raw_prev[-PREVIOUS_CHAPTER_ENDING_CHARS:].lstrip() if raw_prev else ""
            else:
                prev_text, prev_ending = _load_previous_chapter_context_from_db(
                    db,
                    project_id=task.project_id,
                    outline_id=task.outline_id,
                    chapter_number=int(chapter.number),
                    previous_chapter=mode,
                )

            smart_recent_summaries = ""
            smart_recent_full = ""
            smart_story_skeleton = ""
            if params.include_smart_context:
                smart_recent_summaries, smart_recent_full, smart_story_skeleton = build_smart_context(
                    db,
                    project_id=task.project_id,
                    outline_id=task.outline_id,
                    chapter_number=int(chapter.number),
                )

        chapter_request_id = f"batch:{task_id}:{str(chapter_id or '')[:8]}"
        base_instruction = params.instruction
        instruction = f"【替换模式】输出完整替换稿（整章）。\n{base_instruction}".strip()

        requirements_obj: dict[str, object] = {}
        if params.target_word_count is not None:
            requirements_obj["target_word_count"] = params.target_word_count
        requirements_text = json.dumps(requirements_obj, ensure_ascii=False, indent=2) if requirements_obj else ""

        values: dict[str, object] = {
            "mode": "replace",
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": outline_text,
            "chapter_number": str(chapter_number),
            "chapter_title": (chapter.title or ""),
            "chapter_plan": (chapter.plan or ""),
            "requirements": requirements_text,
            "target_word_count": str(params.target_word_count or ""),
            "instruction": instruction,
            "previous_chapter": prev_text,
            "previous_chapter_ending": prev_ending,
            "current_draft_tail": "",
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
            "chapter_number": int(chapter_number),
            "chapter_title": (chapter.title or ""),
            "chapter_plan": (chapter.plan or ""),
            "previous_chapter": prev_text,
            "previous_chapter_ending": prev_ending,
            "mode": "replace",
            "current_draft_tail": "",
            "smart_context_recent_summaries": smart_recent_summaries,
            "smart_context_recent_full": smart_recent_full,
            "smart_context_story_skeleton": smart_story_skeleton,
        }
        values["user"] = {"instruction": instruction, "requirements": requirements_obj}

        try:
            llm_call = llm_call_base
            prompt_system = ""
            prompt_user = ""
            prompt_messages = []
            prompt_render_log_json: str | None = None
            render_values = values

            if params.plan_first:
                with SessionLocal() as db:
                    ensure_default_plan_preset(db, project_id=task.project_id)
                    plan_values = dict(values)
                    plan_values["instruction"] = base_instruction
                    plan_values["user"] = {"instruction": base_instruction, "requirements": requirements_obj}
                    plan_system, plan_user, plan_messages, _, _, _, plan_render_log = render_preset_for_task(
                        db,
                        project_id=task.project_id,
                        task="plan_chapter",
                        values=plan_values,  # type: ignore[arg-type]
                        macro_seed=f"{chapter_request_id}:plan",
                        provider=llm_call.provider,
                    )
                plan_render_log_json = json.dumps(plan_render_log, ensure_ascii=False)
                plan_call = with_param_overrides(llm_call, {"temperature": 0.2, "max_tokens": 1024})
                plan_result = call_llm_and_record(
                    logger=logger,
                    request_id=f"{chapter_request_id}:plan",
                    actor_user_id=actor_user_id,
                    project_id=task.project_id,
                    chapter_id=chapter_id,
                    run_type="plan_chapter",
                    api_key=str(resolved_api_key),
                    prompt_system=plan_system,
                    prompt_user=plan_user,
                    prompt_messages=plan_messages,
                    prompt_render_log_json=plan_render_log_json,
                    llm_call=plan_call,
                )

                plan_contract = contract_for_task("plan_chapter")
                plan_parsed = plan_contract.parse(plan_result.text, finish_reason=plan_result.finish_reason)
                plan_text = str((plan_parsed.data or {}).get("plan") or "").strip()
                if plan_text:
                    instruction_with_plan = f"{str(render_values.get('instruction') or '').rstrip()}\n\n<PLAN>\n{plan_text}\n</PLAN>"
                    render_values = dict(render_values)
                    render_values["instruction"] = instruction_with_plan
                    render_values["story_plan"] = plan_text

                    story = render_values.get("story")
                    if isinstance(story, dict):
                        story2 = dict(story)
                        story2["plan"] = plan_text
                        render_values["story"] = story2
                    else:
                        render_values["story"] = {"plan": plan_text}

                    user_ns = render_values.get("user")
                    if isinstance(user_ns, dict):
                        user2 = dict(user_ns)
                        user2["instruction"] = instruction_with_plan
                        render_values["user"] = user2

            with SessionLocal() as db:
                prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
                    db,
                    project_id=task.project_id,
                    task="chapter_generate",
                    values=render_values,  # type: ignore[arg-type]
                    macro_seed=chapter_request_id,
                    provider=llm_call.provider,
                )
            prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)

            if params.target_word_count is not None:
                llm_call = with_param_overrides(
                    llm_call,
                    {"max_tokens": estimate_max_tokens(target_word_count=params.target_word_count, provider=llm_call.provider)},
                )

            llm_result = call_llm_and_record(
                logger=logger,
                request_id=chapter_request_id,
                actor_user_id=actor_user_id,
                project_id=task.project_id,
                chapter_id=chapter_id,
                run_type="chapter",
                api_key=str(resolved_api_key),
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                prompt_messages=prompt_messages,
                prompt_render_log_json=prompt_render_log_json,
                llm_call=llm_call,
            )

            chapter_contract = contract_for_task("chapter_generate")
            parsed = chapter_contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
            data = parsed.data

            if params.post_edit:
                raw_content = str(data.get("content_md") or "").strip()
                if raw_content:
                    with SessionLocal() as db:
                        ensure_default_post_edit_preset(db, project_id=task.project_id)
                        post_values = dict(render_values)
                        post_values["raw_content"] = raw_content

                        story_ns = post_values.get("story")
                        if isinstance(story_ns, dict):
                            story2 = dict(story_ns)
                            story2["raw_content"] = raw_content
                            post_values["story"] = story2
                        else:
                            post_values["story"] = {"raw_content": raw_content}

                        post_system, post_user, post_messages, _, _, _, post_render_log = render_preset_for_task(
                            db,
                            project_id=task.project_id,
                            task="post_edit",
                            values=post_values,  # type: ignore[arg-type]
                            macro_seed=f"{chapter_request_id}:post_edit",
                            provider=llm_call.provider,
                        )
                    post_render_log_json = json.dumps(post_render_log, ensure_ascii=False)
                    post_call = with_param_overrides(llm_call, {"temperature": 0.4})
                    post_result = call_llm_and_record(
                        logger=logger,
                        request_id=f"{chapter_request_id}:post_edit",
                        actor_user_id=actor_user_id,
                        project_id=task.project_id,
                        chapter_id=chapter_id,
                        run_type="post_edit",
                        api_key=str(resolved_api_key),
                        prompt_system=post_system,
                        prompt_user=post_user,
                        prompt_messages=post_messages,
                        prompt_render_log_json=post_render_log_json,
                        llm_call=post_call,
                    )
                    post_contract = contract_for_task("post_edit")
                    post_parsed = post_contract.parse(post_result.text, finish_reason=post_result.finish_reason)
                    edited = str(post_parsed.data.get("content_md") or "").strip()
                    if post_parsed.parse_error is None and edited:
                        data["content_md"] = edited

            final_content = str(data.get("content_md") or "").strip()
            final_summary = str(data.get("summary") or "").strip()
            prev_content_md = final_content
            prev_summary = final_summary

            with SessionLocal() as db:
                task = db.get(BatchGenerationTask, task_id)
                item = db.get(BatchGenerationTaskItem, item_id)
                if task is None or item is None:
                    return
                item.status = "succeeded"
                item.generation_run_id = llm_result.run_id
                item.error_message = None
                task.completed_count = int(task.completed_count or 0) + 1
                db.commit()
        except AppError as exc:
            log_event(
                logger,
                "warning",
                batch_generation={
                    "task_id": task_id,
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "error_code": exc.code,
                },
            )
            with SessionLocal() as db:
                task = db.get(BatchGenerationTask, task_id)
                item = db.get(BatchGenerationTaskItem, item_id)
                if task is not None:
                    task.status = "failed"
                    task.error_json = json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False)
                if item is not None:
                    item.status = "failed"
                    item.error_message = f"{exc.message} ({exc.code})"
                db.commit()
            return
        except Exception as exc:
            log_event(
                logger,
                "error",
                batch_generation={
                    "task_id": task_id,
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "exception_type": type(exc).__name__,
                },
            )
            with SessionLocal() as db:
                task = db.get(BatchGenerationTask, task_id)
                item = db.get(BatchGenerationTaskItem, item_id)
                if task is not None:
                    task.status = "failed"
                    task.error_json = json.dumps({"code": "INTERNAL_ERROR", "message": "批量生成失败"}, ensure_ascii=False)
                if item is not None:
                    item.status = "failed"
                    item.error_message = "批量生成失败"
                db.commit()
            return

    with SessionLocal() as db:
        task = db.get(BatchGenerationTask, task_id)
        if task is None:
            return
        if task.cancel_requested:
            task.status = "canceled"
        elif task.status != "failed":
            task.status = "succeeded"
        db.commit()
