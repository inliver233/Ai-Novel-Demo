from __future__ import annotations

import json
import logging

from app.api.deps import require_chapter_editor
from app.core.errors import AppError
from app.core.logging import log_event
from app.db.session import SessionLocal
from app.models.project import Project
from app.schemas.chapter_analysis import ChapterAnalyzeRequest, ChapterRewriteRequest
from app.schemas.memory_update import MemoryUpdateV1Request
from app.services.chapter_analysis_models import (
    PreparedChapterAnalyzeRequest,
    PreparedChapterAutoMemoryUpdateRequest,
    PreparedChapterRewriteRequest,
)
from app.services.chapter_context_service import build_chapter_analyze_render_values, build_chapter_rewrite_render_values
from app.services.generation_service import RecordedLlmResult, call_llm_and_record, with_param_overrides
from app.services.llm_task_preset_resolver import resolve_task_llm_config
from app.services.memory_update_service import propose_chapter_memory_change_set
from app.services.output_contracts import contract_for_task
from app.services.prompt_presets import (
    _ensure_default_preset_from_resource,
    ensure_default_chapter_analyze_preset,
    ensure_default_chapter_rewrite_preset,
    render_preset_for_task,
)

logger = logging.getLogger("ainovel")


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


def _prompt_missing(*, prompt_system: str, prompt_user: str) -> bool:
    return not prompt_system.strip() and not prompt_user.strip()


def _apply_llm_contract_payload(*, task_key: str, llm_result: RecordedLlmResult) -> dict[str, object]:
    contract = contract_for_task(task_key)
    parsed = contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
    data = dict(parsed.data)
    data["generation_run_id"] = llm_result.run_id
    data["latency_ms"] = llm_result.latency_ms
    if llm_result.dropped_params:
        data["dropped_params"] = llm_result.dropped_params
    if parsed.warnings:
        data["warnings"] = parsed.warnings
    if parsed.parse_error is not None:
        data["parse_error"] = parsed.parse_error
    if llm_result.finish_reason is not None:
        data["finish_reason"] = llm_result.finish_reason
    return data


def _has_analysis_draft_overrides(body: ChapterAnalyzeRequest) -> bool:
    return any(
        value is not None
        for value in (body.draft_title, body.draft_plan, body.draft_summary, body.draft_content_md)
    )


def _prepare_auto_memory_update_request(
    *,
    db,
    request_id: str,
    chapter,
    project: Project,
    body: ChapterAnalyzeRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> PreparedChapterAutoMemoryUpdateRequest | None:
    if not bool(getattr(body, "auto_propose_memory_update", False)):
        return None

    skip_reason: str | None = None
    if _has_analysis_draft_overrides(body):
        skip_reason = "draft_override"

    chapter_status = str(getattr(chapter, "status", "") or "").strip().lower()
    if chapter_status != "done":
        skip_reason = skip_reason or "chapter_not_done"

    if skip_reason is not None:
        return PreparedChapterAutoMemoryUpdateRequest(enabled=True, skip_reason=skip_reason)

    project_id = str(chapter.project_id)
    _ensure_default_preset_from_resource(db, project_id=project_id, resource_key="memory_update_v1", activate=True)
    resolved_memupd = resolve_task_llm_for_call(
        db=db,
        project=project,
        user_id=user_id,
        task_key="memory_update",
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    values = {
        "chapter_id": str(chapter.id),
        "chapter_number": int(chapter.number),
        "chapter_title": str(chapter.title or ""),
        "chapter_plan": str(chapter.plan or ""),
        "chapter_content_md": str(chapter.content_md or ""),
        "focus": str(getattr(body, "memory_update_focus", "") or "").strip(),
    }
    prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
        db,
        project_id=project_id,
        task="memory_update",
        values=values,
        macro_seed=f"{request_id}:memory_update",
        provider=resolved_memupd.llm_call.provider,
    )
    idempotency_key = str(getattr(body, "memory_update_idempotency_key", "") or "").strip() or None
    return PreparedChapterAutoMemoryUpdateRequest(
        enabled=True,
        resolved_api_key=str(resolved_memupd.api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=json.dumps(render_log, ensure_ascii=False),
        llm_call=resolved_memupd.llm_call,
        idempotency_key=idempotency_key,
    )


def prepare_chapter_analyze_request(
    *,
    request_id: str,
    chapter_id: str,
    body: ChapterAnalyzeRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> PreparedChapterAnalyzeRequest:
    with SessionLocal() as db:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        project_id = str(chapter.project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        resolved_analyze = resolve_task_llm_for_call(
            db=db,
            project=project,
            user_id=user_id,
            task_key="chapter_analyze",
            x_llm_provider=x_llm_provider,
            x_llm_api_key=x_llm_api_key,
        )
        ensure_default_chapter_analyze_preset(db, project_id=project_id, activate=True)
        values = build_chapter_analyze_render_values(db, project=project, chapter=chapter, body=body)
        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="chapter_analyze",
            values=values,  # type: ignore[arg-type]
            macro_seed=f"{request_id}:analyze",
            provider=resolved_analyze.llm_call.provider,
        )
        auto_memory_update = _prepare_auto_memory_update_request(
            db=db,
            request_id=request_id,
            chapter=chapter,
            project=project,
            body=body,
            user_id=user_id,
            x_llm_provider=x_llm_provider,
            x_llm_api_key=x_llm_api_key,
        )

    return PreparedChapterAnalyzeRequest(
        project_id=project_id,
        resolved_api_key=str(resolved_analyze.api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=json.dumps(render_log, ensure_ascii=False),
        llm_call=resolved_analyze.llm_call,
        auto_memory_update=auto_memory_update,
    )


def _build_auto_memory_update_result(
    *,
    request_id: str,
    chapter_id: str,
    user_id: str,
    project_id: str,
    analyze_run_id: str,
    prepared: PreparedChapterAutoMemoryUpdateRequest,
    fallback_api_key: str,
) -> dict[str, object]:
    if prepared.skip_reason is not None:
        return {"enabled": True, "ok": False, "skipped": True, "reason": prepared.skip_reason}
    if prepared.llm_call is None:
        return {"enabled": True, "ok": False, "skipped": True, "reason": "memupd_prepare_failed"}
    if _prompt_missing(prompt_system=prepared.prompt_system, prompt_user=prepared.prompt_user):
        return {"enabled": True, "ok": False, "skipped": True, "reason": "memupd_prompt_missing"}

    try:
        llm_call = with_param_overrides(prepared.llm_call, {"temperature": 0.2, "max_tokens": 2048})
        llm_result = call_llm_and_record(
            logger=logger,
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            chapter_id=chapter_id,
            run_type="memory_update_auto_propose",
            api_key=prepared.resolved_api_key or fallback_api_key,
            prompt_system=prepared.prompt_system,
            prompt_user=prepared.prompt_user,
            prompt_messages=prepared.prompt_messages,
            prompt_render_log_json=prepared.prompt_render_log_json,
            llm_call=llm_call,
        )
        contract = contract_for_task("memory_update")
        parsed = contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
        if parsed.parse_error is not None:
            return {
                "enabled": True,
                "ok": False,
                "skipped": True,
                "reason": "memupd_parse_error",
                "llm_generation_run_id": llm_result.run_id,
                "finish_reason": llm_result.finish_reason,
                "parse_error": parsed.parse_error,
                "warnings": parsed.warnings,
            }

        idempotency_key = prepared.idempotency_key or f"anlz-memupd-{str(analyze_run_id or '')[:8]}"
        payload = MemoryUpdateV1Request(
            schema_version="memory_update_v1",
            idempotency_key=idempotency_key,
            title=str(parsed.data.get("title") or "Memory Update (auto)").strip() or "Memory Update (auto)",
            summary_md=str(parsed.data.get("summary_md") or "").strip() or None,
            ops=list(parsed.data.get("ops") or []),
        )

        with SessionLocal() as db:
            chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
            status = str(getattr(chapter, "status", "") or "").strip().lower()
            if status != "done":
                return {
                    "enabled": True,
                    "ok": False,
                    "skipped": True,
                    "reason": "chapter_not_done",
                    "llm_generation_run_id": llm_result.run_id,
                }
            out = propose_chapter_memory_change_set(
                db=db,
                request_id=request_id,
                actor_user_id=user_id,
                chapter=chapter,
                payload=payload,
            )

        change_set = out.get("change_set") if isinstance(out, dict) else None
        change_set_id = change_set.get("id") if isinstance(change_set, dict) else None
        return {
            "enabled": True,
            "ok": True,
            "skipped": False,
            "idempotent": bool(out.get("idempotent")) if isinstance(out, dict) else False,
            "change_set_id": change_set_id,
            "llm_generation_run_id": llm_result.run_id,
        }
    except AppError as exc:
        return {
            "enabled": True,
            "ok": False,
            "skipped": True,
            "reason": "memupd_error",
            "error": {"code": str(exc.code), "message": str(exc.message)},
        }
    except Exception as exc:  # pragma: no cover - defensive branch
        log_event(logger, "warning", event="CHAPTER_ANALYZE_AUTO_MEMUPD_FAILED", chapter_id=chapter_id, error=str(exc))
        return {
            "enabled": True,
            "ok": False,
            "skipped": True,
            "reason": "memupd_error",
            "error": {"code": "INTERNAL_ERROR", "message": "自动记忆更新生成失败"},
        }


def analyze_chapter(
    *,
    request_id: str,
    chapter_id: str,
    body: ChapterAnalyzeRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> dict[str, object]:
    prepared = prepare_chapter_analyze_request(
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    if _prompt_missing(prompt_system=prepared.prompt_system, prompt_user=prepared.prompt_user):
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 chapter_analyze 提示词预设/提示块", status_code=400)

    llm_call = with_param_overrides(prepared.llm_call, {"temperature": 0.2, "max_tokens": 2048})
    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=prepared.project_id,
        chapter_id=chapter_id,
        run_type="chapter_analyze",
        api_key=prepared.resolved_api_key,
        prompt_system=prepared.prompt_system,
        prompt_user=prepared.prompt_user,
        prompt_messages=prepared.prompt_messages,
        prompt_render_log_json=prepared.prompt_render_log_json,
        llm_call=llm_call,
    )
    data = _apply_llm_contract_payload(task_key="chapter_analyze", llm_result=llm_result)

    if prepared.auto_memory_update is not None and prepared.auto_memory_update.enabled:
        data["memory_update_auto_propose"] = _build_auto_memory_update_result(
            request_id=request_id,
            chapter_id=chapter_id,
            user_id=user_id,
            project_id=prepared.project_id,
            analyze_run_id=llm_result.run_id,
            prepared=prepared.auto_memory_update,
            fallback_api_key=prepared.resolved_api_key,
        )
    return data


def prepare_chapter_rewrite_request(
    *,
    request_id: str,
    chapter_id: str,
    body: ChapterRewriteRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> PreparedChapterRewriteRequest:
    if not body.analysis:
        raise AppError.validation(message="章节分析结果不能为空（analysis），请先完成章节分析")

    analysis_json = json.dumps(body.analysis, ensure_ascii=False, indent=2)
    with SessionLocal() as db:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        project_id = str(chapter.project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        resolved_rewrite = resolve_task_llm_for_call(
            db=db,
            project=project,
            user_id=user_id,
            task_key="chapter_rewrite",
            x_llm_provider=x_llm_provider,
            x_llm_api_key=x_llm_api_key,
        )
        ensure_default_chapter_rewrite_preset(db, project_id=project_id, activate=True)
        draft_content_md = body.draft_content_md if body.draft_content_md is not None else (chapter.content_md or "")
        if not draft_content_md.strip():
            raise AppError.validation(message="当前章节正文为空，无法重写")

        values = build_chapter_rewrite_render_values(
            db,
            project=project,
            chapter=chapter,
            body=body,
            analysis_json=analysis_json,
            draft_content_md=draft_content_md,
        )
        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="chapter_rewrite",
            values=values,  # type: ignore[arg-type]
            macro_seed=f"{request_id}:rewrite",
            provider=resolved_rewrite.llm_call.provider,
        )

    return PreparedChapterRewriteRequest(
        project_id=project_id,
        resolved_api_key=str(resolved_rewrite.api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=json.dumps(render_log, ensure_ascii=False),
        llm_call=resolved_rewrite.llm_call,
    )


def rewrite_chapter(
    *,
    request_id: str,
    chapter_id: str,
    body: ChapterRewriteRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> dict[str, object]:
    prepared = prepare_chapter_rewrite_request(
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    if _prompt_missing(prompt_system=prepared.prompt_system, prompt_user=prepared.prompt_user):
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 chapter_rewrite 提示词预设/提示块", status_code=400)

    llm_call = with_param_overrides(prepared.llm_call, {"temperature": 0.35, "max_tokens": 8192})
    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=prepared.project_id,
        chapter_id=chapter_id,
        run_type="chapter_rewrite",
        api_key=prepared.resolved_api_key,
        prompt_system=prepared.prompt_system,
        prompt_user=prepared.prompt_user,
        prompt_messages=prepared.prompt_messages,
        prompt_render_log_json=prepared.prompt_render_log_json,
        llm_call=llm_call,
    )
    return _apply_llm_contract_payload(task_key="chapter_rewrite", llm_result=llm_result)
