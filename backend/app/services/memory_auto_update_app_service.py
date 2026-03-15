from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.api.deps import require_chapter_editor
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.user import User
from app.schemas.memory_update import MemoryUpdateV1Request
from app.services.generation_service import PreparedLlmCall, call_llm_and_record, with_param_overrides
from app.services.llm_task_preset_resolver import resolve_task_llm_config
from app.services.memory_update_service import propose_chapter_memory_change_set
from app.services.output_contracts import contract_for_task
from app.services.prompt_presets import _ensure_default_preset_from_resource, render_preset_for_task

logger = logging.getLogger("ainovel")


@dataclass(frozen=True, slots=True)
class PreparedMemoryAutoProposeRequest:
    project_id: str
    resolved_api_key: str
    prompt_system: str
    prompt_user: str
    prompt_messages: list[object]
    prompt_render_log_json: str | None
    llm_call: PreparedLlmCall
    idempotency_key: str


def resolve_task_llm_for_call(
    *,
    db,
    project: Project,
    user_id: str,
    task_key: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
):
    resolved = resolve_task_llm_config(
        db,
        project=project,
        user_id=user_id,
        task_key=task_key,
        header_api_key=x_llm_api_key,
    )
    if resolved is None:
        raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
    if x_llm_api_key and x_llm_provider and resolved.llm_call.provider != x_llm_provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="当前任务 provider 与请求头不一致，请先保存/切换", status_code=400)
    return resolved


def require_chapter_done_for_memory_update(*, db, chapter: Chapter, user_id: str, allow_draft: bool) -> None:
    status = str(getattr(chapter, "status", "") or "").strip().lower()
    if status == "done":
        return

    if allow_draft:
        actor = db.get(User, user_id)
        if actor is None or not bool(getattr(actor, "is_admin", False)):
            raise AppError.forbidden()
        return

    raise AppError.conflict(
        message="仅定稿章节可进行记忆更新",
        details={"reason": "chapter_not_done", "chapter_status": str(getattr(chapter, "status", "") or "")},
    )


def prepare_memory_auto_propose_request(
    *,
    request_id: str,
    chapter_id: str,
    focus: str,
    user_id: str,
    allow_draft: bool,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
    idempotency_key: str,
) -> PreparedMemoryAutoProposeRequest:
    with SessionLocal() as db:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)
        project_id = str(chapter.project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        resolved_memupd = resolve_task_llm_for_call(
            db=db,
            project=project,
            user_id=user_id,
            task_key="memory_update",
            x_llm_provider=x_llm_provider,
            x_llm_api_key=x_llm_api_key,
        )
        resolved_api_key = str(resolved_memupd.api_key)

        _ensure_default_preset_from_resource(db, project_id=project_id, resource_key="memory_update_v1", activate=True)
        values = {
            "chapter_id": str(chapter.id),
            "chapter_number": int(chapter.number),
            "chapter_title": str(chapter.title or ""),
            "chapter_plan": str(chapter.plan or ""),
            "chapter_content_md": str(chapter.content_md or ""),
            "focus": focus,
        }

        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="memory_update",
            values=values,
            macro_seed=f"{request_id}:memory_update",
            provider=resolved_memupd.llm_call.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)
        llm_call = resolved_memupd.llm_call

    if not prompt_system.strip() and not prompt_user.strip():
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 memory_update 提示词预设/提示块", status_code=400)

    return PreparedMemoryAutoProposeRequest(
        project_id=project_id,
        resolved_api_key=resolved_api_key,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
        llm_call=llm_call,
        idempotency_key=idempotency_key,
    )


def auto_propose_chapter_memory_update(
    *,
    request_id: str,
    chapter_id: str,
    focus: str,
    user_id: str,
    allow_draft: bool,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
    idempotency_key: str,
) -> dict[str, object]:
    prepared = prepare_memory_auto_propose_request(
        request_id=request_id,
        chapter_id=chapter_id,
        focus=focus,
        user_id=user_id,
        allow_draft=allow_draft,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
        idempotency_key=idempotency_key,
    )

    llm_call = with_param_overrides(prepared.llm_call, {"temperature": 0.2, "max_tokens": 2048})
    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=prepared.project_id,
        chapter_id=chapter_id,
        run_type="memory_update_auto_propose",
        api_key=prepared.resolved_api_key,
        prompt_system=prepared.prompt_system,
        prompt_user=prepared.prompt_user,
        prompt_messages=prepared.prompt_messages,
        prompt_render_log_json=prepared.prompt_render_log_json,
        llm_call=llm_call,
    )

    contract = contract_for_task("memory_update")
    parsed = contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
    if parsed.parse_error is not None:
        details = {
            "parse_error": parsed.parse_error,
            "warnings": parsed.warnings,
            "generation_run_id": llm_result.run_id,
            "llm_generation_run_id": llm_result.run_id,
            "finish_reason": llm_result.finish_reason,
        }
        raise AppError.validation(message="记忆更新（memory_update）输出不符合 JSON 契约", details=details)

    payload = MemoryUpdateV1Request(
        schema_version="memory_update_v1",
        idempotency_key=prepared.idempotency_key,
        title=str(parsed.data.get("title") or "Memory Update (auto)").strip() or "Memory Update (auto)",
        summary_md=str(parsed.data.get("summary_md") or "").strip() or None,
        ops=list(parsed.data.get("ops") or []),
    )

    with SessionLocal() as db:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)
        out = propose_chapter_memory_change_set(
            db=db,
            request_id=request_id,
            actor_user_id=user_id,
            chapter=chapter,
            payload=payload,
        )
    out["llm_generation_run_id"] = llm_result.run_id
    return out
