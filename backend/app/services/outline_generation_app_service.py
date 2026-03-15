from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select

from app.api.deps import require_project_editor
from app.core.errors import AppError
from app.core.logging import log_event
from app.db.session import SessionLocal
from app.llm.client import call_llm_stream_messages
from app.llm.messages import ChatMessage
from app.models.character import Character
from app.models.project_settings import ProjectSettings
from app.schemas.outline_generate import OutlineGenerateRequest
from app.services.generation_service import (
    PreparedLlmCall,
    build_run_params_json,
    call_llm_and_record,
    with_param_overrides,
)
from app.services.llm_task_preset_resolver import resolve_task_llm_config
from app.services.output_contracts import build_repair_prompt_for_task, contract_for_task
from app.services.prompt_presets import render_preset_for_task
from app.services.prompt_store import format_characters
from app.services.run_store import write_generation_run
from app.services.style_resolution_service import resolve_style_guide
from app.utils.sse_response import (
    sse_chunk,
    sse_done,
    sse_error,
    sse_heartbeat,
    sse_progress,
    sse_result,
)

logger = logging.getLogger("ainovel")

OutlineFillProgressHook = Callable[[dict[str, object]], None]
OutlineSegmentProgressHook = Callable[[dict[str, object]], None]


def _outline_route():
    from app.api.routes import outline as outline_route

    return outline_route


@dataclass(frozen=True, slots=True)
class PreparedOutlineGeneration:
    resolved_api_key: str
    prompt_system: str
    prompt_user: str
    prompt_messages: list[ChatMessage]
    prompt_render_log_json: str
    llm_call: PreparedLlmCall
    target_chapter_count: int | None
    run_params_extra_json: dict[str, object]
    run_params_json: str


@dataclass(frozen=True, slots=True)
class OutlineSegmentGenerationResult:
    data: dict[str, object]
    warnings: list[str]
    parse_error: dict[str, object] | None
    run_ids: list[str]
    latency_ms: int
    dropped_params: list[str]
    finish_reasons: list[str]
    meta: dict[str, object]


def prepare_outline_generation(
    *,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: str,
    request_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> PreparedOutlineGeneration:
    outline_route = _outline_route()

    with SessionLocal() as db:
        project = require_project_editor(db, project_id=project_id, user_id=user_id)
        resolved_outline = resolve_task_llm_config(
            db,
            project=project,
            user_id=user_id,
            task_key="outline_generate",
            header_api_key=x_llm_api_key,
        )
        if resolved_outline is None:
            raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
        if x_llm_api_key and x_llm_provider and resolved_outline.llm_call.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前任务 provider 与请求头不一致，请先保存/切换", status_code=400)
        resolved_api_key = str(resolved_outline.api_key)

        settings_row = db.get(ProjectSettings, project_id)
        world_setting = (settings_row.world_setting if settings_row else "") or ""
        settings_style_guide = (settings_row.style_guide if settings_row else "") or ""
        constraints = (settings_row.constraints if settings_row else "") or ""

        style_resolution: dict[str, object] = {"style_id": None, "source": "disabled"}
        if not body.context.include_world_setting:
            world_setting = ""
            settings_style_guide = ""
            constraints = ""
        else:
            resolved_style_guide, style_resolution = resolve_style_guide(
                db,
                project_id=project_id,
                user_id=user_id,
                requested_style_id=body.style_id,
                include_style_guide=True,
                settings_style_guide=settings_style_guide,
            )
            settings_style_guide = resolved_style_guide

        run_params_extra_json: dict[str, object] = {"style_resolution": style_resolution}

        chars: list[Character] = []
        if body.context.include_characters:
            chars = db.execute(select(Character).where(Character.project_id == project_id)).scalars().all()
        characters_text = format_characters(chars)
        target_chapter_count = outline_route._extract_target_chapter_count(body.requirements)
        guidance = outline_route._build_outline_generation_guidance(target_chapter_count)

        requirements_text = json.dumps(body.requirements or {}, ensure_ascii=False, indent=2)
        values: dict[str, object] = {
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": settings_style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": "",
            "chapter_number": "",
            "chapter_title": "",
            "chapter_plan": "",
            "requirements": requirements_text,
            "instruction": "",
            "previous_chapter": "",
            "target_chapter_count": target_chapter_count or "",
            "chapter_count_rule": guidance.get("chapter_count_rule", ""),
            "chapter_detail_rule": guidance.get("chapter_detail_rule", ""),
        }

        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="outline_generate",
            values=values,
            macro_seed=request_id,
            provider=resolved_outline.llm_call.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)

        llm_call = resolved_outline.llm_call
        current_max_tokens = llm_call.params.get("max_tokens")
        current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
        wanted_max_tokens = outline_route._recommend_outline_max_tokens(
            target_chapter_count=target_chapter_count,
            provider=llm_call.provider,
            model=llm_call.model,
            current_max_tokens=current_max_tokens_int,
        )
        if isinstance(wanted_max_tokens, int) and wanted_max_tokens > 0:
            llm_call = with_param_overrides(llm_call, {"max_tokens": wanted_max_tokens})
            run_params_extra_json["outline_auto_max_tokens"] = {
                "target_chapter_count": target_chapter_count,
                "from": current_max_tokens_int,
                "to": wanted_max_tokens,
            }

    run_params_json = build_run_params_json(
        params_json=llm_call.params_json,
        memory_retrieval_log_json=None,
        extra_json=run_params_extra_json,
    )
    return PreparedOutlineGeneration(
        resolved_api_key=resolved_api_key,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
        llm_call=llm_call,
        target_chapter_count=target_chapter_count,
        run_params_extra_json=run_params_extra_json,
        run_params_json=run_params_json,
    )


def _build_outline_segment_aggregate_output_text(
    *,
    data: dict[str, object],
    warnings: list[str],
    meta: dict[str, object],
) -> str:
    chapters = data.get("chapters")
    chapter_count = len(chapters) if isinstance(chapters, list) else 0
    coverage = data.get("chapter_coverage")
    summary: dict[str, object] = {
        "mode": "segmented",
        "chapter_count": chapter_count,
        "warnings": warnings[:40],
        "segmented_generation": meta,
    }
    if isinstance(coverage, dict):
        summary["chapter_coverage"] = {
            "target_chapter_count": coverage.get("target_chapter_count"),
            "missing_count": coverage.get("missing_count"),
            "missing_numbers_preview": (coverage.get("missing_numbers") or [])[:30]
            if isinstance(coverage.get("missing_numbers"), list)
            else [],
        }
    return json.dumps(summary, ensure_ascii=False)


def _write_outline_segmented_aggregate_run(
    *,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    run_type: str,
    llm_call: PreparedLlmCall,
    prompt_system: str,
    prompt_user: str,
    prompt_render_log_json: str | None,
    run_params_json: str,
    data: dict[str, object],
    warnings: list[str],
    parse_error: dict[str, object] | None,
    segmented_run_ids: list[str],
    meta: dict[str, object],
) -> str:
    output_text = _build_outline_segment_aggregate_output_text(data=data, warnings=warnings, meta=meta)
    error_json: str | None = None
    if parse_error is not None:
        error_payload = {
            "code": str(parse_error.get("code") or "OUTLINE_PARSE_ERROR"),
            "message": str(parse_error.get("message") or "分段生成结果不完整"),
            "details": {
                "segmented_run_ids": segmented_run_ids,
                "segmented_generation": meta,
            },
        }
        error_json = json.dumps(error_payload, ensure_ascii=False)
    return write_generation_run(
        request_id=request_id,
        actor_user_id=actor_user_id,
        project_id=project_id,
        chapter_id=None,
        run_type=run_type,
        provider=llm_call.provider,
        model=llm_call.model,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_render_log_json=prompt_render_log_json,
        params_json=run_params_json,
        output_text=output_text,
        error_json=error_json,
    )


def _repair_outline_remaining_gaps_final_sweep_with_llm(
    *,
    chapters_now: list[dict[str, object]],
    outline_md: str,
    target_chapter_count: int,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    api_key: str,
    llm_call,
    run_params_extra_json: dict[str, object] | None,
    progress_hook: OutlineFillProgressHook | None = None,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    outline_route = _outline_route()

    warnings: list[str] = []
    run_ids: list[str] = []
    missing_numbers = outline_route._collect_missing_chapter_numbers(
        chapters_now, target_chapter_count=target_chapter_count
    )
    if not missing_numbers:
        return chapters_now, warnings, run_ids
    if len(missing_numbers) > outline_route.OUTLINE_GAP_REPAIR_FINAL_SWEEP_MAX_MISSING:
        warnings.append("outline_gap_repair_final_sweep_skipped_too_many_missing")
        return chapters_now, warnings, run_ids

    warnings.append("outline_gap_repair_final_sweep_started")
    max_attempts = outline_route.OUTLINE_GAP_REPAIR_FINAL_SWEEP_ATTEMPTS_PER_CHAPTER
    contract = contract_for_task("outline_generate")
    if progress_hook is not None:
        progress_hook(
            {
                "event": "gap_repair_final_sweep_start",
                "attempt": 0,
                "max_attempts": max_attempts,
                "remaining_count": len(missing_numbers),
            }
        )

    for number in list(missing_numbers):
        chapter_fixed = False
        last_failure_reason: str | None = None
        last_output_numbers: list[int] | None = None
        for attempt in range(1, max_attempts + 1):
            remaining_before = len(
                outline_route._collect_missing_chapter_numbers(
                    chapters_now, target_chapter_count=target_chapter_count
                )
            )
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "gap_repair_final_sweep_attempt_start",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": remaining_before,
                        "range": str(number),
                    }
                )

            repair_system, repair_user = outline_route._build_outline_gap_repair_prompts(
                target_chapter_count=target_chapter_count,
                batch_missing=[number],
                existing_chapters=chapters_now,
                outline_md=outline_md,
                attempt=attempt,
                max_attempts=max_attempts,
                previous_output_numbers=last_output_numbers,
                previous_failure_reason=last_failure_reason,
            )
            current_max_tokens = llm_call.params.get("max_tokens")
            current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
            repair_max_tokens = outline_route._recommend_outline_segment_max_tokens(
                requested_count=1,
                provider=llm_call.provider,
                model=llm_call.model,
                current_max_tokens=current_max_tokens_int,
            )
            repair_call = with_param_overrides(llm_call, {"max_tokens": repair_max_tokens}) if repair_max_tokens else llm_call
            repair_extra = dict(run_params_extra_json or {})
            repair_extra["outline_gap_repair_final_sweep"] = {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "target_chapter_count": target_chapter_count,
                "chapter_number": number,
            }
            try:
                repaired = call_llm_and_record(
                    logger=logger,
                    request_id=request_id,
                    actor_user_id=actor_user_id,
                    project_id=project_id,
                    chapter_id=None,
                    run_type="outline_gap_repair_final_sweep",
                    api_key=api_key,
                    prompt_system=repair_system,
                    prompt_user=repair_user,
                    llm_call=repair_call,
                    run_params_extra_json=repair_extra,
                )
            except AppError as exc:
                warnings.append("outline_gap_repair_final_sweep_call_failed")
                if exc.code == "LLM_TIMEOUT":
                    warnings.append("outline_gap_repair_final_sweep_timeout")
                last_failure_reason = f"模型调用失败（{exc.code}）"
                last_output_numbers = None
                continue

            run_ids.append(repaired.run_id)
            raw_preview = outline_route._build_outline_stream_raw_preview(repaired.text)
            raw_chars = len(repaired.text or "")
            repaired_parsed = contract.parse(repaired.text, finish_reason=repaired.finish_reason)
            repaired_data, repaired_warnings, repaired_error = (
                repaired_parsed.data,
                repaired_parsed.warnings,
                repaired_parsed.parse_error,
            )
            warnings.extend(repaired_warnings)
            if repaired_error is not None:
                warnings.append("outline_gap_repair_final_sweep_parse_failed")
                last_failure_reason = str(repaired_error.get("message") or "输出解析失败")
                last_output_numbers = None
                continue

            incoming, incoming_warnings = outline_route._normalize_outline_chapters(repaired_data.get("chapters"))
            warnings.extend(incoming_warnings)
            incoming_numbers = outline_route._extract_outline_chapter_numbers(incoming, limit=120)
            if not incoming:
                warnings.append("outline_gap_repair_final_sweep_empty")
                last_failure_reason = "未输出可识别章节"
                last_output_numbers = incoming_numbers
                continue

            by_number = {
                int(c["number"]): c for c in chapters_now if int(c["number"]) <= target_chapter_count
            }
            accepted = 0
            accepted_numbers: list[int] = []
            for chapter in incoming:
                chapter_number = int(chapter["number"])
                if chapter_number != number:
                    continue
                previous = by_number.get(chapter_number)
                if previous is None:
                    by_number[chapter_number] = chapter
                    accepted += 1
                    accepted_numbers.append(chapter_number)
                    continue
                if outline_route._chapter_score(chapter) > outline_route._chapter_score(previous):
                    by_number[chapter_number] = chapter

            if accepted <= 0:
                warnings.append("outline_gap_repair_final_sweep_no_progress")
                if incoming_numbers:
                    last_failure_reason = "输出章号与目标章号不一致"
                else:
                    last_failure_reason = "未输出可采纳章节"
                last_output_numbers = incoming_numbers
                continue

            warnings.append("outline_gap_repair_final_sweep_applied")
            last_failure_reason = None
            last_output_numbers = None
            chapters_now = [by_number[n] for n in sorted(by_number.keys())]
            chapter_fixed = True
            remaining_after = len(
                outline_route._collect_missing_chapter_numbers(
                    chapters_now, target_chapter_count=target_chapter_count
                )
            )
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "gap_repair_final_sweep_applied",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "accepted": accepted,
                        "accepted_numbers": accepted_numbers,
                        "chapters_snapshot": outline_route._clone_outline_chapters(chapters_now),
                        "chapter_count": len(chapters_now),
                        "remaining_count": remaining_after,
                        "raw_output_preview": raw_preview,
                        "raw_output_chars": raw_chars,
                    }
                )
            break

        if not chapter_fixed:
            warnings.append("outline_gap_repair_final_sweep_chapter_unresolved")

    remaining_final = len(
        outline_route._collect_missing_chapter_numbers(chapters_now, target_chapter_count=target_chapter_count)
    )
    if progress_hook is not None:
        progress_hook(
            {
                "event": "gap_repair_final_sweep_done",
                "attempt": max_attempts,
                "max_attempts": max_attempts,
                "remaining_count": remaining_final,
            }
        )
    return chapters_now, outline_route._dedupe_warnings(warnings), run_ids


def _repair_outline_remaining_gaps_with_llm(
    *,
    data: dict[str, object],
    target_chapter_count: int | None,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    api_key: str,
    llm_call,
    run_params_extra_json: dict[str, object] | None,
    progress_hook: OutlineFillProgressHook | None = None,
) -> tuple[dict[str, object], list[str], list[str]]:
    outline_route = _outline_route()

    if not target_chapter_count or target_chapter_count <= 0:
        return data, [], []
    chapters_now, normalize_warnings = outline_route._normalize_outline_chapters(data.get("chapters"))
    if not chapters_now:
        return data, normalize_warnings, []

    missing_numbers = outline_route._collect_missing_chapter_numbers(
        chapters_now, target_chapter_count=target_chapter_count
    )
    if not missing_numbers:
        return data, [], []

    warnings: list[str] = list(normalize_warnings)
    run_ids: list[str] = []
    if len(missing_numbers) > outline_route.OUTLINE_GAP_REPAIR_MAX_MISSING:
        warnings.append("outline_gap_repair_skipped_too_many_missing")
        return data, outline_route._dedupe_warnings(warnings), run_ids

    max_attempts = outline_route._outline_gap_repair_max_attempts(len(missing_numbers))
    contract = contract_for_task("outline_generate")
    attempt = 0
    stagnant_rounds = 0
    last_failure_reason: str | None = None
    last_output_numbers: list[int] | None = None

    if progress_hook is not None:
        progress_hook(
            {
                "event": "gap_repair_start",
                "attempt": 0,
                "max_attempts": max_attempts,
                "remaining_count": len(missing_numbers),
            }
        )

    while attempt < max_attempts:
        missing_numbers = outline_route._collect_missing_chapter_numbers(
            chapters_now, target_chapter_count=target_chapter_count
        )
        if not missing_numbers:
            break
        attempt += 1
        batch_missing = missing_numbers[: outline_route.OUTLINE_GAP_REPAIR_BATCH_SIZE]
        if progress_hook is not None:
            progress_hook(
                {
                    "event": "gap_repair_attempt_start",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "batch_size": len(batch_missing),
                    "remaining_count": len(missing_numbers),
                    "range": outline_route._format_chapter_number_ranges(batch_missing),
                }
            )

        repair_system, repair_user = outline_route._build_outline_gap_repair_prompts(
            target_chapter_count=target_chapter_count,
            batch_missing=batch_missing,
            existing_chapters=chapters_now,
            outline_md=str(data.get("outline_md") or ""),
            attempt=attempt,
            max_attempts=max_attempts,
            previous_output_numbers=last_output_numbers,
            previous_failure_reason=last_failure_reason,
        )

        current_max_tokens = llm_call.params.get("max_tokens")
        current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
        repair_max_tokens = outline_route._recommend_outline_segment_max_tokens(
            requested_count=len(batch_missing),
            provider=llm_call.provider,
            model=llm_call.model,
            current_max_tokens=current_max_tokens_int,
        )
        repair_call = with_param_overrides(llm_call, {"max_tokens": repair_max_tokens}) if repair_max_tokens else llm_call
        repair_extra = dict(run_params_extra_json or {})
        repair_extra["outline_gap_repair"] = {
            "attempt": attempt,
            "max_attempts": max_attempts,
            "target_chapter_count": target_chapter_count,
            "batch_missing": batch_missing,
        }
        try:
            repaired = call_llm_and_record(
                logger=logger,
                request_id=request_id,
                actor_user_id=actor_user_id,
                project_id=project_id,
                chapter_id=None,
                run_type="outline_gap_repair",
                api_key=api_key,
                prompt_system=repair_system,
                prompt_user=repair_user,
                llm_call=repair_call,
                run_params_extra_json=repair_extra,
            )
        except AppError as exc:
            warnings.append("outline_gap_repair_call_failed")
            if exc.code == "LLM_TIMEOUT":
                warnings.append("outline_gap_repair_timeout")
            last_failure_reason = f"模型调用失败（{exc.code}）"
            last_output_numbers = None
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "gap_repair_call_failed",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": len(missing_numbers),
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_GAP_REPAIR_STAGNANT_LIMIT:
                break
            continue

        run_ids.append(repaired.run_id)
        raw_preview = outline_route._build_outline_stream_raw_preview(repaired.text)
        raw_chars = len(repaired.text or "")
        repaired_parsed = contract.parse(repaired.text, finish_reason=repaired.finish_reason)
        repaired_data, repaired_warnings, repaired_error = (
            repaired_parsed.data,
            repaired_parsed.warnings,
            repaired_parsed.parse_error,
        )
        warnings.extend(repaired_warnings)
        if repaired_error is not None:
            warnings.append("outline_gap_repair_parse_failed")
            last_failure_reason = str(repaired_error.get("message") or "输出解析失败")
            last_output_numbers = None
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "gap_repair_parse_failed",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": len(missing_numbers),
                        "raw_output_preview": raw_preview,
                        "raw_output_chars": raw_chars,
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_GAP_REPAIR_STAGNANT_LIMIT:
                break
            continue

        incoming, incoming_warnings = outline_route._normalize_outline_chapters(repaired_data.get("chapters"))
        warnings.extend(incoming_warnings)
        incoming_numbers = outline_route._extract_outline_chapter_numbers(incoming, limit=120)
        if not incoming:
            warnings.append("outline_gap_repair_empty")
            last_failure_reason = "未输出可识别章节"
            last_output_numbers = incoming_numbers
            stagnant_rounds += 1
            if stagnant_rounds >= outline_route.OUTLINE_GAP_REPAIR_STAGNANT_LIMIT:
                break
            continue

        accepted = 0
        accepted_numbers: list[int] = []
        allowed = set(batch_missing)
        by_number = {
            int(c["number"]): c for c in chapters_now if int(c["number"]) <= target_chapter_count
        }
        for chapter in incoming:
            number = int(chapter["number"])
            if number not in allowed:
                continue
            previous = by_number.get(number)
            if previous is None:
                by_number[number] = chapter
                accepted += 1
                accepted_numbers.append(number)
                continue
            if outline_route._chapter_score(chapter) > outline_route._chapter_score(previous):
                by_number[number] = chapter

        if accepted <= 0:
            warnings.append("outline_gap_repair_no_progress")
            last_output_numbers = incoming_numbers
            if incoming_numbers:
                last_failure_reason = "输出章号与缺失章号不一致"
            else:
                last_failure_reason = "未输出可采纳章节"
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "gap_repair_no_progress",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": len(missing_numbers),
                        "raw_output_preview": raw_preview,
                        "raw_output_chars": raw_chars,
                        "incoming_numbers_text": outline_route._format_chapter_number_ranges(incoming_numbers),
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_GAP_REPAIR_STAGNANT_LIMIT:
                break
            continue

        warnings.append("outline_gap_repair_applied")
        stagnant_rounds = 0
        last_failure_reason = None
        last_output_numbers = None
        chapters_now = [by_number[n] for n in sorted(by_number.keys())]
        remaining = len(
            outline_route._collect_missing_chapter_numbers(
                chapters_now, target_chapter_count=target_chapter_count
            )
        )
        if progress_hook is not None:
            progress_hook(
                {
                    "event": "gap_repair_applied",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "accepted": accepted,
                    "accepted_numbers": accepted_numbers,
                    "chapters_snapshot": outline_route._clone_outline_chapters(chapters_now),
                    "chapter_count": len(chapters_now),
                    "remaining_count": remaining,
                    "raw_output_preview": raw_preview,
                    "raw_output_chars": raw_chars,
                }
            )

    data["chapters"] = chapters_now
    data, coverage_warnings = outline_route._enforce_outline_chapter_coverage(
        data=data, target_chapter_count=target_chapter_count
    )
    warnings.extend(coverage_warnings)
    coverage = data.get("chapter_coverage")
    remaining_count = int(coverage.get("missing_count") or 0) if isinstance(coverage, dict) else 0
    if remaining_count > 0:
        warnings.append("outline_gap_repair_remaining")
        chapters_now, final_warnings, final_run_ids = _repair_outline_remaining_gaps_final_sweep_with_llm(
            chapters_now=chapters_now,
            outline_md=str(data.get("outline_md") or ""),
            target_chapter_count=target_chapter_count,
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            api_key=api_key,
            llm_call=llm_call,
            run_params_extra_json=run_params_extra_json,
            progress_hook=progress_hook,
        )
        warnings.extend(final_warnings)
        for run_id in final_run_ids:
            if run_id not in run_ids:
                run_ids.append(run_id)
        data["chapters"] = chapters_now
        data, final_coverage_warnings = outline_route._enforce_outline_chapter_coverage(
            data=data, target_chapter_count=target_chapter_count
        )
        warnings.extend(final_coverage_warnings)
        coverage = data.get("chapter_coverage")
        remaining_count = int(coverage.get("missing_count") or 0) if isinstance(coverage, dict) else 0
        if remaining_count > 0:
            warnings.append("outline_gap_repair_final_sweep_remaining")
        else:
            warnings.extend(["outline_gap_repair_final_sweep_resolved", "outline_gap_repair_resolved"])
    else:
        warnings.append("outline_gap_repair_resolved")

    if progress_hook is not None:
        progress_hook(
            {
                "event": "gap_repair_done",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "remaining_count": remaining_count,
            }
        )
    return data, outline_route._dedupe_warnings(warnings), run_ids


def _fill_outline_missing_chapters_with_llm(
    *,
    data: dict[str, object],
    target_chapter_count: int | None,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    api_key: str,
    llm_call,
    run_params_extra_json: dict[str, object] | None,
    progress_hook: OutlineFillProgressHook | None = None,
) -> tuple[dict[str, object], list[str], list[str]]:
    outline_route = _outline_route()

    if not target_chapter_count or target_chapter_count <= 0:
        return data, [], []
    chapters_now, normalize_warnings = outline_route._normalize_outline_chapters(data.get("chapters"))
    if not chapters_now:
        return data, normalize_warnings, []

    warnings: list[str] = list(normalize_warnings)
    continue_run_ids: list[str] = []
    contract = contract_for_task("outline_generate")
    missing_numbers = outline_route._collect_missing_chapter_numbers(
        chapters_now, target_chapter_count=target_chapter_count
    )
    max_attempts = outline_route._outline_fill_max_attempts_for_missing(len(missing_numbers))
    stagnant_rounds = 0
    attempt = 0

    if progress_hook is not None:
        progress_hook(
            {
                "event": "fill_start",
                "attempt": 0,
                "max_attempts": max_attempts,
                "remaining_count": len(missing_numbers),
            }
        )

    while attempt < max_attempts:
        missing_numbers = outline_route._collect_missing_chapter_numbers(
            chapters_now, target_chapter_count=target_chapter_count
        )
        if not missing_numbers:
            break
        batch_size = outline_route._outline_fill_batch_size_for_missing(len(missing_numbers))
        batch_missing = missing_numbers[:batch_size]
        attempt += 1
        if progress_hook is not None:
            progress_hook(
                {
                    "event": "attempt_start",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "batch_size": len(batch_missing),
                    "remaining_count": len(missing_numbers),
                }
            )
        fill_system, fill_user = outline_route._build_outline_missing_chapters_prompts(
            target_chapter_count=target_chapter_count,
            missing_numbers=batch_missing,
            existing_chapters=chapters_now,
            outline_md=str(data.get("outline_md") or ""),
        )
        current_max_tokens = llm_call.params.get("max_tokens")
        current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
        fill_max_tokens = outline_route._recommend_outline_max_tokens(
            target_chapter_count=max(41, len(batch_missing) + 20),
            provider=llm_call.provider,
            model=llm_call.model,
            current_max_tokens=current_max_tokens_int,
        )
        fill_call = with_param_overrides(llm_call, {"max_tokens": fill_max_tokens}) if fill_max_tokens else llm_call
        fill_extra = dict(run_params_extra_json or {})
        fill_extra["outline_fill_missing"] = {
            "attempt": attempt,
            "max_attempts": max_attempts,
            "target_chapter_count": target_chapter_count,
            "batch_missing": batch_missing,
        }
        try:
            filled = call_llm_and_record(
                logger=logger,
                request_id=request_id,
                actor_user_id=actor_user_id,
                project_id=project_id,
                chapter_id=None,
                run_type="outline_fill_missing",
                api_key=api_key,
                prompt_system=fill_system,
                prompt_user=fill_user,
                llm_call=fill_call,
                run_params_extra_json=fill_extra,
            )
        except AppError as exc:
            warnings.append("outline_fill_missing_call_failed")
            if exc.code == "LLM_TIMEOUT":
                warnings.append("outline_fill_missing_timeout")
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "attempt_call_failed",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error_code": exc.code,
                        "remaining_count": len(missing_numbers),
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue
        continue_run_ids.append(filled.run_id)
        fill_raw_preview = outline_route._build_outline_stream_raw_preview(filled.text)
        fill_raw_chars = len(filled.text or "")
        filled_parsed = contract.parse(filled.text, finish_reason=filled.finish_reason)
        filled_data, filled_warnings, filled_error = (
            filled_parsed.data,
            filled_parsed.warnings,
            filled_parsed.parse_error,
        )
        warnings.extend(filled_warnings)
        if filled_error is not None:
            warnings.append("outline_fill_missing_parse_failed")
            if filled.finish_reason == "length":
                warnings.append("outline_fill_missing_truncated")
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "attempt_parse_failed",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": len(missing_numbers),
                        "raw_output_preview": fill_raw_preview,
                        "raw_output_chars": fill_raw_chars,
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue

        incoming, incoming_warnings = outline_route._normalize_outline_chapters(filled_data.get("chapters"))
        warnings.extend(incoming_warnings)
        if not incoming:
            warnings.append("outline_fill_missing_empty")
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "attempt_empty",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": len(missing_numbers),
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue

        accepted = 0
        accepted_numbers: list[int] = []
        allowed = set(batch_missing)
        by_number = {
            int(c["number"]): c for c in chapters_now if int(c["number"]) <= target_chapter_count
        }
        for chapter in incoming:
            number = int(chapter["number"])
            if number not in allowed:
                continue
            previous = by_number.get(number)
            if previous is None:
                by_number[number] = chapter
                accepted += 1
                accepted_numbers.append(number)
                continue
            if outline_route._chapter_score(chapter) > outline_route._chapter_score(previous):
                by_number[number] = chapter

        if accepted <= 0:
            warnings.append("outline_fill_missing_no_progress")
            stagnant_rounds += 1
            if progress_hook is not None:
                progress_hook(
                    {
                        "event": "attempt_no_progress",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "remaining_count": len(missing_numbers),
                    }
                )
            if stagnant_rounds >= outline_route.OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue

        warnings.append("outline_fill_missing_applied")
        stagnant_rounds = 0
        chapters_now = [by_number[n] for n in sorted(by_number.keys())]
        remaining = len(
            outline_route._collect_missing_chapter_numbers(
                chapters_now, target_chapter_count=target_chapter_count
            )
        )
        if progress_hook is not None:
            chapter_snapshot = outline_route._clone_outline_chapters(chapters_now)
            progress_hook(
                {
                    "event": "attempt_applied",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "accepted": accepted,
                    "accepted_numbers": accepted_numbers,
                    "chapters_snapshot": chapter_snapshot,
                    "chapter_count": len(chapter_snapshot),
                    "remaining_count": remaining,
                    "raw_output_preview": fill_raw_preview,
                    "raw_output_chars": fill_raw_chars,
                }
            )

    data["chapters"] = chapters_now
    data, coverage_warnings = outline_route._enforce_outline_chapter_coverage(
        data=data, target_chapter_count=target_chapter_count
    )
    warnings.extend(coverage_warnings)
    coverage = data.get("chapter_coverage")
    remaining_count = int(coverage.get("missing_count") or 0) if isinstance(coverage, dict) else 0

    gap_repair_run_ids: list[str] = []
    if remaining_count > 0:
        repaired_data, repair_warnings, repair_run_ids = _repair_outline_remaining_gaps_with_llm(
            data=data,
            target_chapter_count=target_chapter_count,
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            api_key=api_key,
            llm_call=llm_call,
            run_params_extra_json=run_params_extra_json,
            progress_hook=progress_hook,
        )
        data = repaired_data
        warnings.extend(repair_warnings)
        gap_repair_run_ids = repair_run_ids
        for run_id in repair_run_ids:
            if run_id not in continue_run_ids:
                continue_run_ids.append(run_id)

    coverage = data.get("chapter_coverage")
    remaining_count = int(coverage.get("missing_count") or 0) if isinstance(coverage, dict) else 0
    if remaining_count > 0:
        warnings.append("outline_fill_missing_remaining")
    if gap_repair_run_ids and isinstance(coverage, dict):
        coverage["gap_repair_run_ids"] = gap_repair_run_ids
        data["chapter_coverage"] = coverage
    if progress_hook is not None:
        progress_hook(
            {
                "event": "fill_done",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "remaining_count": remaining_count,
            }
        )
    return data, outline_route._dedupe_warnings(warnings), continue_run_ids


def _generate_outline_segmented_with_llm(
    *,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    api_key: str,
    llm_call: PreparedLlmCall,
    prompt_system: str,
    prompt_user: str,
    target_chapter_count: int,
    run_params_extra_json: dict[str, object] | None,
    progress_hook: OutlineSegmentProgressHook | None = None,
) -> OutlineSegmentGenerationResult:
    outline_route = _outline_route()

    warnings: list[str] = ["outline_segment_mode_enabled"]
    run_ids: list[str] = []
    dropped_params: list[str] = []
    finish_reasons: list[str] = []
    latency_ms_total = 0
    outline_md = ""
    chapters_by_number: dict[int, dict[str, object]] = {}
    batch_size = outline_route._outline_segment_batch_size_for_target(target_chapter_count)
    batches = outline_route._outline_segment_batches(target_chapter_count, batch_size=batch_size)
    batch_count = len(batches)
    parse_error: dict[str, object] | None = None

    def _emit_progress(payload: dict[str, object]) -> None:
        if progress_hook is None:
            return
        try:
            progress_hook(payload)
        except Exception:
            return

    _emit_progress(
        {
            "event": "segment_start",
            "batch_count": batch_count,
            "target_chapter_count": target_chapter_count,
            "completed_count": 0,
            "remaining_count": target_chapter_count,
            "progress_percent": 12,
        }
    )

    for batch_index, batch in enumerate(batches, start=1):
        missing_numbers = [n for n in batch if n not in chapters_by_number]
        if not missing_numbers:
            continue
        max_attempts = outline_route._outline_segment_max_attempts_for_batch(len(batch))
        stagnant_attempts = 0
        attempt = 0
        last_failure_reason: str | None = None
        last_output_numbers: list[int] | None = None

        while missing_numbers and attempt < max_attempts:
            attempt += 1
            range_text = outline_route._format_chapter_number_ranges(batch)
            _emit_progress(
                {
                    "event": "batch_attempt_start",
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "range": range_text,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "target_chapter_count": target_chapter_count,
                    "completed_count": len(chapters_by_number),
                    "remaining_count": target_chapter_count - len(chapters_by_number),
                    "progress_percent": 12 + int((batch_index - 1) / max(1, batch_count) * 70),
                }
            )
            existing = [chapters_by_number[n] for n in sorted(chapters_by_number.keys())]
            segment_system, segment_user = outline_route._build_outline_segment_prompts(
                base_prompt_system=prompt_system,
                base_prompt_user=prompt_user,
                target_chapter_count=target_chapter_count,
                batch_numbers=missing_numbers,
                existing_chapters=existing,
                existing_outline_md=outline_md,
                attempt=attempt,
                max_attempts=max_attempts,
                previous_output_numbers=last_output_numbers,
                previous_failure_reason=last_failure_reason,
            )

            current_max_tokens = llm_call.params.get("max_tokens")
            current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
            segment_max_tokens = outline_route._recommend_outline_segment_max_tokens(
                requested_count=len(missing_numbers),
                provider=llm_call.provider,
                model=llm_call.model,
                current_max_tokens=current_max_tokens_int,
            )
            segment_call = with_param_overrides(llm_call, {"max_tokens": segment_max_tokens}) if segment_max_tokens else llm_call

            segment_extra = dict(run_params_extra_json or {})
            segment_extra["outline_segment"] = {
                "batch_index": batch_index,
                "batch_count": batch_count,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "target_chapter_count": target_chapter_count,
                "batch_numbers": missing_numbers,
            }
            try:
                segment_res = call_llm_and_record(
                    logger=logger,
                    request_id=request_id,
                    actor_user_id=actor_user_id,
                    project_id=project_id,
                    chapter_id=None,
                    run_type="outline_segment",
                    api_key=api_key,
                    prompt_system=segment_system,
                    prompt_user=segment_user,
                    llm_call=segment_call,
                    run_params_extra_json=segment_extra,
                )
            except AppError as exc:
                warnings.append("outline_segment_call_failed")
                if exc.code == "LLM_TIMEOUT":
                    warnings.append("outline_segment_timeout")
                last_failure_reason = f"模型调用失败（{exc.code}）"
                last_output_numbers = None
                stagnant_attempts += 1
                _emit_progress(
                    {
                        "event": "batch_call_failed",
                        "batch_index": batch_index,
                        "batch_count": batch_count,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "target_chapter_count": target_chapter_count,
                        "completed_count": len(chapters_by_number),
                        "remaining_count": target_chapter_count - len(chapters_by_number),
                        "failure_reason": last_failure_reason,
                        "progress_percent": 12
                        + int(min(1.0, len(chapters_by_number) / max(1, target_chapter_count)) * 70),
                    }
                )
                if stagnant_attempts >= outline_route.OUTLINE_SEGMENT_STAGNANT_ATTEMPTS_LIMIT:
                    break
                continue

            if segment_res.run_id not in run_ids:
                run_ids.append(segment_res.run_id)
            latency_ms_total += int(segment_res.latency_ms or 0)
            if segment_res.finish_reason is not None:
                finish_reasons.append(segment_res.finish_reason)
            for item in segment_res.dropped_params:
                if item not in dropped_params:
                    dropped_params.append(item)
            segment_raw_preview = outline_route._build_outline_stream_raw_preview(segment_res.text)
            segment_raw_chars = len(segment_res.text or "")

            parsed_data, parsed_warnings, parsed_error = outline_route._parse_outline_batch_output(
                text=segment_res.text,
                finish_reason=segment_res.finish_reason,
                fallback_outline_md=outline_md,
            )
            warnings.extend(parsed_warnings)
            if parsed_error is not None:
                warnings.append("outline_segment_parse_failed")
                if segment_res.finish_reason == "length":
                    warnings.append("outline_segment_truncated")
                last_failure_reason = str(parsed_error.get("message") or "输出解析失败")
                last_output_numbers = None
                _emit_progress(
                    {
                        "event": "batch_parse_failed",
                        "batch_index": batch_index,
                        "batch_count": batch_count,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "range": range_text,
                        "target_chapter_count": target_chapter_count,
                        "completed_count": len(chapters_by_number),
                        "remaining_count": target_chapter_count - len(chapters_by_number),
                        "raw_output_preview": segment_raw_preview,
                        "raw_output_chars": segment_raw_chars,
                        "failure_reason": last_failure_reason,
                        "progress_percent": 12
                        + int(min(1.0, len(chapters_by_number) / max(1, target_chapter_count)) * 70),
                    }
                )
                stagnant_attempts += 1
                if stagnant_attempts >= outline_route.OUTLINE_SEGMENT_STAGNANT_ATTEMPTS_LIMIT:
                    break
                continue

            parsed_outline_md = str(parsed_data.get("outline_md") or "").strip()
            if parsed_outline_md and not outline_md:
                outline_md = parsed_outline_md

            incoming = parsed_data.get("chapters")
            incoming_chapters = incoming if isinstance(incoming, list) else []
            incoming_numbers = outline_route._extract_outline_chapter_numbers(incoming_chapters, limit=120)
            accepted, accepted_numbers = outline_route._merge_segment_chapters(
                by_number=chapters_by_number,
                incoming=incoming_chapters,
                allowed_numbers=set(missing_numbers),
            )
            if accepted <= 0:
                warnings.append("outline_segment_no_progress")
                missing_set = set(missing_numbers)
                overlap_numbers = [n for n in incoming_numbers if n in missing_set]
                if incoming_numbers and not overlap_numbers:
                    last_failure_reason = "输出章号与当前批次不匹配（疑似重复旧章节）"
                elif incoming_numbers:
                    last_failure_reason = "输出章号包含目标范围，但未形成可采纳新章节"
                else:
                    last_failure_reason = "未输出可识别章节"
                last_output_numbers = incoming_numbers
                _emit_progress(
                    {
                        "event": "batch_no_progress",
                        "batch_index": batch_index,
                        "batch_count": batch_count,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "range": range_text,
                        "incoming_numbers": incoming_numbers,
                        "incoming_numbers_text": outline_route._format_chapter_number_ranges(incoming_numbers),
                        "target_chapter_count": target_chapter_count,
                        "completed_count": len(chapters_by_number),
                        "remaining_count": target_chapter_count - len(chapters_by_number),
                        "raw_output_preview": segment_raw_preview,
                        "raw_output_chars": segment_raw_chars,
                        "failure_reason": last_failure_reason,
                        "progress_percent": 12
                        + int(min(1.0, len(chapters_by_number) / max(1, target_chapter_count)) * 70),
                    }
                )
                stagnant_attempts += 1
                if stagnant_attempts >= outline_route.OUTLINE_SEGMENT_STAGNANT_ATTEMPTS_LIMIT:
                    break
                continue

            warnings.append("outline_segment_applied")
            last_failure_reason = None
            last_output_numbers = None
            stagnant_attempts = 0
            missing_numbers = [n for n in batch if n not in chapters_by_number]
            chapters_snapshot = outline_route._clone_outline_chapters(
                [chapters_by_number[n] for n in sorted(chapters_by_number.keys())]
            )
            _emit_progress(
                {
                    "event": "batch_applied",
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "range": range_text,
                    "accepted": accepted,
                    "accepted_numbers": accepted_numbers,
                    "chapters_snapshot": chapters_snapshot,
                    "outline_md": outline_md,
                    "target_chapter_count": target_chapter_count,
                    "completed_count": len(chapters_snapshot),
                    "remaining_count": target_chapter_count - len(chapters_snapshot),
                    "raw_output_preview": segment_raw_preview,
                    "raw_output_chars": segment_raw_chars,
                    "progress_percent": 12
                    + int(min(1.0, len(chapters_snapshot) / max(1, target_chapter_count)) * 80),
                }
            )

        if missing_numbers:
            warnings.append("outline_segment_batch_incomplete")
            chapters_snapshot = outline_route._clone_outline_chapters(
                [chapters_by_number[n] for n in sorted(chapters_by_number.keys())]
            )
            _emit_progress(
                {
                    "event": "batch_incomplete",
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "range": outline_route._format_chapter_number_ranges(batch),
                    "target_chapter_count": target_chapter_count,
                    "completed_count": len(chapters_snapshot),
                    "remaining_count": target_chapter_count - len(chapters_snapshot),
                    "progress_percent": 90,
                }
            )

    chapters_now = [chapters_by_number[n] for n in sorted(chapters_by_number.keys())]
    if not outline_md:
        outline_md = "## AI 大纲\n\n- 分段生成完成，请按需要补充总纲摘要。"
        warnings.append("outline_segment_outline_md_fallback")
    data: dict[str, object] = {"outline_md": outline_md, "chapters": chapters_now}
    data, coverage_warnings = outline_route._enforce_outline_chapter_coverage(
        data=data, target_chapter_count=target_chapter_count
    )
    warnings.extend(coverage_warnings)

    def _forward_fill_progress(update: dict[str, object]) -> None:
        if not isinstance(update, dict):
            return
        mapped = dict(update)
        mapped["event"] = f"fill_{mapped.get('event')}"
        mapped["target_chapter_count"] = target_chapter_count
        chapters_snapshot = mapped.get("chapters_snapshot")
        if isinstance(chapters_snapshot, list):
            mapped["completed_count"] = len(chapters_snapshot)
        else:
            chapter_count_raw = mapped.get("chapter_count")
            if isinstance(chapter_count_raw, int):
                mapped["completed_count"] = chapter_count_raw
            else:
                mapped["completed_count"] = len(data.get("chapters") or [])
        mapped["progress_percent"] = 94
        _emit_progress(mapped)

    data, fill_warnings, fill_run_ids = _fill_outline_missing_chapters_with_llm(
        data=data,
        target_chapter_count=target_chapter_count,
        request_id=request_id,
        actor_user_id=actor_user_id,
        project_id=project_id,
        api_key=api_key,
        llm_call=llm_call,
        run_params_extra_json=run_params_extra_json,
        progress_hook=_forward_fill_progress if progress_hook is not None else None,
    )
    warnings.extend(fill_warnings)
    for rid in fill_run_ids:
        if rid not in run_ids:
            run_ids.append(rid)

    chapters_final = data.get("chapters")
    chapters_final_count = len(chapters_final) if isinstance(chapters_final, list) else 0
    if chapters_final_count <= 0:
        parse_error = {"code": "OUTLINE_PARSE_ERROR", "message": "分段生成未得到可用章节结构"}

    coverage = data.get("chapter_coverage")
    if isinstance(coverage, dict):
        coverage["segment_batch_size"] = batch_size
        coverage["segment_batch_count"] = batch_count
        coverage["segment_run_ids"] = run_ids
        data["chapter_coverage"] = coverage

    _emit_progress(
        {
            "event": "segment_done",
            "batch_count": batch_count,
            "target_chapter_count": target_chapter_count,
            "completed_count": chapters_final_count,
            "remaining_count": max(0, target_chapter_count - chapters_final_count),
            "progress_percent": 98,
        }
    )

    meta: dict[str, object] = {
        "mode": "segmented",
        "target_chapter_count": target_chapter_count,
        "batch_size": batch_size,
        "batch_count": batch_count,
        "run_count": len(run_ids),
    }
    return OutlineSegmentGenerationResult(
        data=data,
        warnings=outline_route._dedupe_warnings(warnings),
        parse_error=parse_error,
        run_ids=run_ids,
        latency_ms=latency_ms_total,
        dropped_params=dropped_params,
        finish_reasons=finish_reasons,
        meta=meta,
    )


def generate_outline(
    *,
    request_id: str,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> dict[str, object]:
    outline_route = _outline_route()
    prepared = prepare_outline_generation(
        project_id=project_id,
        body=body,
        user_id=user_id,
        request_id=request_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )

    if outline_route._should_use_outline_segmented_mode(prepared.target_chapter_count):
        assert prepared.target_chapter_count is not None
        segmented = _generate_outline_segmented_with_llm(
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            api_key=str(prepared.resolved_api_key),
            llm_call=prepared.llm_call,
            prompt_system=prepared.prompt_system,
            prompt_user=prepared.prompt_user,
            target_chapter_count=prepared.target_chapter_count,
            run_params_extra_json=prepared.run_params_extra_json,
        )
        aggregate_run_id = _write_outline_segmented_aggregate_run(
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            run_type="outline_segmented",
            llm_call=prepared.llm_call,
            prompt_system=prepared.prompt_system,
            prompt_user=prepared.prompt_user,
            prompt_render_log_json=prepared.prompt_render_log_json,
            run_params_json=prepared.run_params_json,
            data=segmented.data,
            warnings=segmented.warnings,
            parse_error=segmented.parse_error,
            segmented_run_ids=segmented.run_ids,
            meta=segmented.meta,
        )
        data = dict(segmented.data)
        warnings = outline_route._dedupe_warnings(segmented.warnings)
        if warnings:
            data["warnings"] = warnings
        if segmented.parse_error is not None:
            data["parse_error"] = segmented.parse_error
        data["generation_run_id"] = aggregate_run_id
        if segmented.run_ids:
            data["generation_sub_run_ids"] = segmented.run_ids
            data["generation_run_ids"] = [aggregate_run_id, *segmented.run_ids]
        if segmented.latency_ms > 0:
            data["latency_ms"] = segmented.latency_ms
        if segmented.dropped_params:
            data["dropped_params"] = segmented.dropped_params
        if segmented.finish_reasons:
            data["finish_reason"] = segmented.finish_reasons[-1]
            data["finish_reasons"] = segmented.finish_reasons
        data["segmented_generation"] = segmented.meta
        return data

    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=None,
        run_type="outline",
        api_key=str(prepared.resolved_api_key),
        prompt_system=prepared.prompt_system,
        prompt_user=prepared.prompt_user,
        prompt_messages=prepared.prompt_messages,
        prompt_render_log_json=prepared.prompt_render_log_json,
        llm_call=prepared.llm_call,
        run_params_extra_json=prepared.run_params_extra_json,
    )

    raw_output = llm_result.text
    finish_reason = llm_result.finish_reason
    contract = contract_for_task("outline_generate")
    parsed = contract.parse(raw_output, finish_reason=finish_reason)
    data, warnings, parse_error = parsed.data, parsed.warnings, parsed.parse_error

    if parse_error is not None and prepared.llm_call.provider in (
        "openai",
        "openai_responses",
        "openai_compatible",
        "openai_responses_compatible",
    ):
        try:
            repair = build_repair_prompt_for_task("outline_generate", raw_output=raw_output)
            if repair is None:
                raise AppError(code="OUTLINE_FIX_UNSUPPORTED", message="该任务不支持输出修复", status_code=400)
            fix_system, fix_user, fix_run_type = repair
            fix_call = with_param_overrides(prepared.llm_call, {"temperature": 0, "max_tokens": 1024})
            fixed = call_llm_and_record(
                logger=logger,
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                chapter_id=None,
                run_type=fix_run_type,
                api_key=str(prepared.resolved_api_key),
                prompt_system=fix_system,
                prompt_user=fix_user,
                llm_call=fix_call,
                run_params_extra_json=prepared.run_params_extra_json,
            )
            fixed_parsed = contract.parse(fixed.text)
            fixed_data, fixed_warnings, fixed_error = (
                fixed_parsed.data,
                fixed_parsed.warnings,
                fixed_parsed.parse_error,
            )
            if fixed_error is None and fixed_data.get("chapters"):
                fixed_data["raw_output"] = raw_output
                fixed_data["fixed_json"] = fixed_data.get("raw_json") or fixed.text
                data = fixed_data
                warnings.extend(["json_fixed_via_llm", *fixed_warnings])
                parse_error = None
        except AppError:
            warnings.append("outline_fix_json_failed")

    if parse_error is None:
        data, coverage_warnings = outline_route._enforce_outline_chapter_coverage(
            data=data,
            target_chapter_count=prepared.target_chapter_count,
        )
        warnings.extend(coverage_warnings)
        data, fill_warnings, fill_run_ids = _fill_outline_missing_chapters_with_llm(
            data=data,
            target_chapter_count=prepared.target_chapter_count,
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            api_key=str(prepared.resolved_api_key),
            llm_call=prepared.llm_call,
            run_params_extra_json=prepared.run_params_extra_json,
        )
        warnings.extend(fill_warnings)
        if fill_run_ids:
            coverage = data.get("chapter_coverage")
            if isinstance(coverage, dict):
                coverage["fill_run_ids"] = fill_run_ids
                data["chapter_coverage"] = coverage

    warnings = outline_route._dedupe_warnings(warnings)
    if warnings:
        data["warnings"] = warnings
    if parse_error is not None:
        data["parse_error"] = parse_error
    data["generation_run_id"] = llm_result.run_id
    data["latency_ms"] = llm_result.latency_ms
    if llm_result.dropped_params:
        data["dropped_params"] = llm_result.dropped_params
    if finish_reason is not None:
        data["finish_reason"] = finish_reason
    return data


def prepare_outline_stream_request(
    *,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: str,
    request_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> PreparedOutlineGeneration:
    return prepare_outline_generation(
        project_id=project_id,
        body=body,
        user_id=user_id,
        request_id=request_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )


def generate_outline_stream_events(
    *,
    request_id: str,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: str,
    prepared: PreparedOutlineGeneration,
):
    outline_route = _outline_route()

    yield sse_progress(message="准备生成...", progress=0)

    prompt_system = prepared.prompt_system
    prompt_user = prepared.prompt_user
    prompt_messages = prepared.prompt_messages
    prompt_render_log_json = prepared.prompt_render_log_json
    llm_call = prepared.llm_call
    resolved_api_key = prepared.resolved_api_key
    target_chapter_count = prepared.target_chapter_count
    run_params_extra_json = prepared.run_params_extra_json
    run_params_json = prepared.run_params_json

    if outline_route._should_use_outline_segmented_mode(target_chapter_count):
        if target_chapter_count is None:
            yield sse_error(error="长篇分段模式参数异常", code=500)
            yield sse_done()
            return
        yield sse_progress(message="长篇模式：分段生成中...", progress=10)
        segment_progress_lock = threading.Lock()
        segment_progress_events: list[dict[str, object]] = []

        def _on_segment_progress(update: dict[str, object]) -> None:
            if not isinstance(update, dict):
                return
            with segment_progress_lock:
                segment_progress_events.append(dict(update))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _generate_outline_segmented_with_llm,
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                api_key=str(resolved_api_key),
                llm_call=llm_call,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                target_chapter_count=target_chapter_count,
                run_params_extra_json=run_params_extra_json,
                progress_hook=_on_segment_progress,
            )

            last_ping = 0.0
            last_message = ""
            last_snapshot_key: tuple[str, int, int, int] | None = None
            last_raw_preview_key: tuple[str, int, int, int] | None = None
            while True:
                now = time.monotonic()
                if now - last_ping >= outline_route.OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS:
                    yield sse_heartbeat()
                    last_ping = now
                with segment_progress_lock:
                    pending_snapshots = list(segment_progress_events)
                    segment_progress_events.clear()
                for snapshot in pending_snapshots:
                    event_name = str(snapshot.get("event") or "")
                    batch_idx = int(snapshot.get("batch_index") or 0)
                    attempt = int(snapshot.get("attempt") or 0)
                    completed_count = int(snapshot.get("completed_count") or 0)
                    snapshot_chapters = snapshot.get("chapters_snapshot")
                    snapshot_outline_md = str(snapshot.get("outline_md") or "")
                    if event_name in (
                        "batch_applied",
                        "fill_attempt_applied",
                        "fill_gap_repair_applied",
                        "fill_gap_repair_final_sweep_applied",
                    ) and isinstance(snapshot_chapters, list):
                        snapshot_key = (event_name, batch_idx, attempt, completed_count)
                        if snapshot_key != last_snapshot_key:
                            yield sse_result({"outline_md": snapshot_outline_md, "chapters": snapshot_chapters})
                            last_snapshot_key = snapshot_key
                    raw_preview = str(snapshot.get("raw_output_preview") or "").strip()
                    raw_chars_raw = snapshot.get("raw_output_chars")
                    try:
                        raw_chars = int(raw_chars_raw) if raw_chars_raw is not None else len(raw_preview)
                    except Exception:
                        raw_chars = len(raw_preview)
                    if raw_preview:
                        raw_key = (event_name, batch_idx, attempt, raw_chars)
                        if raw_key != last_raw_preview_key:
                            batch_count_raw = snapshot.get("batch_count")
                            try:
                                batch_count = int(batch_count_raw) if batch_count_raw is not None else 0
                            except Exception:
                                batch_count = 0
                            title_parts = [event_name or "segment"]
                            if batch_idx > 0 and batch_count > 0:
                                title_parts.append(f"batch {batch_idx}/{batch_count}")
                            elif batch_idx > 0:
                                title_parts.append(f"batch {batch_idx}")
                            if attempt > 0:
                                title_parts.append(f"attempt {attempt}")
                            title = " | ".join(title_parts)
                            yield sse_chunk(f"\n\n[{title}]\n{raw_preview}\n")
                            last_raw_preview_key = raw_key
                    progress_percent = snapshot.get("progress_percent")
                    if isinstance(progress_percent, int):
                        progress_num = max(10, min(98, progress_percent))
                    else:
                        progress_num = 10
                    message = outline_route._outline_segment_progress_message(snapshot)
                    if message != last_message:
                        yield sse_progress(message=message, progress=progress_num)
                        last_message = message
                if future.done():
                    break
                time.sleep(outline_route.OUTLINE_FILL_POLL_INTERVAL_SECONDS)

            segmented = future.result()

        aggregate_run_id = _write_outline_segmented_aggregate_run(
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            run_type="outline_stream_segmented",
            llm_call=llm_call,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            prompt_render_log_json=prompt_render_log_json,
            run_params_json=run_params_json,
            data=segmented.data,
            warnings=segmented.warnings,
            parse_error=segmented.parse_error,
            segmented_run_ids=segmented.run_ids,
            meta=segmented.meta,
        )
        data = dict(segmented.data)
        warnings = outline_route._dedupe_warnings(segmented.warnings)
        if warnings:
            data["warnings"] = warnings
        if segmented.parse_error is not None:
            data["parse_error"] = segmented.parse_error
        data["generation_run_id"] = aggregate_run_id
        if segmented.run_ids:
            data["generation_sub_run_ids"] = segmented.run_ids
            data["generation_run_ids"] = [aggregate_run_id, *segmented.run_ids]
        if segmented.latency_ms > 0:
            data["latency_ms"] = segmented.latency_ms
        if segmented.dropped_params:
            data["dropped_params"] = segmented.dropped_params
        if segmented.finish_reasons:
            data["finish_reason"] = segmented.finish_reasons[-1]
            data["finish_reasons"] = segmented.finish_reasons
        data["segmented_generation"] = segmented.meta

        result_data = dict(data)
        result_data.pop("raw_output", None)
        result_data.pop("raw_json", None)
        result_data.pop("fixed_json", None)

        yield sse_progress(message="完成", progress=100, status="success")
        yield sse_result(result_data)
        yield sse_done()
        return

    yield sse_progress(message="调用模型...", progress=10)

    raw_output = ""
    generation_run_id: str | None = None
    finish_reason: str | None = None
    dropped_params: list[str] = []
    latency_ms: int | None = None
    stream_run_written = False

    try:
        stream_iter, state = call_llm_stream_messages(
            provider=llm_call.provider,
            base_url=llm_call.base_url,
            model=llm_call.model,
            api_key=str(resolved_api_key),
            messages=prompt_messages,
            params=llm_call.params,
            timeout_seconds=llm_call.timeout_seconds,
            extra=llm_call.extra,
        )

        last_progress = 10
        last_progress_ts = 0.0
        chunk_count = 0
        try:
            for delta in stream_iter:
                raw_output += delta
                yield sse_chunk(delta)
                chunk_count += 1
                if chunk_count % 12 == 0:
                    yield sse_heartbeat()
                now = time.monotonic()
                if now - last_progress_ts >= 0.8:
                    next_progress = 10 + int(min(1.0, len(raw_output) / 6000.0) * 80)
                    next_progress = max(last_progress, min(90, next_progress))
                    if next_progress != last_progress:
                        last_progress = next_progress
                        yield sse_progress(message="生成中...", progress=next_progress)
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
        generation_run_id = write_generation_run(
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            chapter_id=None,
            run_type="outline_stream",
            provider=llm_call.provider,
            model=llm_call.model,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            prompt_render_log_json=prompt_render_log_json,
            params_json=run_params_json,
            output_text=raw_output,
            error_json=None,
        )
        stream_run_written = True

        yield sse_progress(message="解析输出...", progress=90)
        contract = contract_for_task("outline_generate")
        parsed = contract.parse(raw_output, finish_reason=finish_reason)
        data, warnings, parse_error = parsed.data, parsed.warnings, parsed.parse_error

        if parse_error is not None and llm_call.provider in (
            "openai",
            "openai_responses",
            "openai_compatible",
            "openai_responses_compatible",
        ):
            yield sse_progress(message="尝试修复 JSON...", progress=92)
            repair = build_repair_prompt_for_task("outline_generate", raw_output=raw_output)
            if repair is None:
                warnings.append("outline_fix_json_failed")
                repair = None
            if repair is None:
                raise AppError(code="OUTLINE_FIX_UNSUPPORTED", message="该任务不支持输出修复", status_code=400)
            fix_system, fix_user, fix_run_type = repair
            fix_call = with_param_overrides(llm_call, {"temperature": 0, "max_tokens": 1024})
            try:
                fixed = call_llm_and_record(
                    logger=logger,
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    chapter_id=None,
                    run_type=fix_run_type,
                    api_key=str(resolved_api_key),
                    prompt_system=fix_system,
                    prompt_user=fix_user,
                    llm_call=fix_call,
                    run_params_extra_json=run_params_extra_json,
                )
                fixed_parsed = contract.parse(fixed.text)
                fixed_data, fixed_warnings, fixed_error = (
                    fixed_parsed.data,
                    fixed_parsed.warnings,
                    fixed_parsed.parse_error,
                )
                if fixed_error is None and fixed_data.get("chapters"):
                    fixed_data["raw_output"] = raw_output
                    fixed_data["fixed_json"] = fixed_data.get("raw_json") or fixed.text
                    data = fixed_data
                    warnings.extend(["json_fixed_via_llm", *fixed_warnings])
                    parse_error = None
            except AppError:
                warnings.append("outline_fix_json_failed")

        if parse_error is None:
            data, coverage_warnings = outline_route._enforce_outline_chapter_coverage(
                data=data,
                target_chapter_count=target_chapter_count,
            )
            warnings.extend(coverage_warnings)
            preview_outline_md = str(data.get("outline_md") or "")
            preview_chapters, _preview_warnings = outline_route._normalize_outline_chapters(data.get("chapters"))
            if preview_chapters:
                yield sse_result(
                    {
                        "outline_md": preview_outline_md,
                        "chapters": outline_route._clone_outline_chapters(preview_chapters),
                    }
                )
            if target_chapter_count:
                yield sse_progress(message="补全缺失章节...", progress=94)
            fill_progress_lock = threading.Lock()
            fill_progress_events: list[dict[str, object]] = []

            def _on_fill_progress(update: dict[str, object]) -> None:
                if not isinstance(update, dict):
                    return
                with fill_progress_lock:
                    fill_progress_events.append(dict(update))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                fill_future = executor.submit(
                    _fill_outline_missing_chapters_with_llm,
                    data=data,
                    target_chapter_count=target_chapter_count,
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    api_key=str(resolved_api_key),
                    llm_call=llm_call,
                    run_params_extra_json=run_params_extra_json,
                    progress_hook=_on_fill_progress,
                )

                last_ping = 0.0
                last_message = ""
                last_snapshot_marker: tuple[str, int] | None = None
                while True:
                    now = time.monotonic()
                    if now - last_ping >= outline_route.OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS:
                        yield sse_heartbeat()
                        last_ping = now
                    with fill_progress_lock:
                        pending_fill_snapshots = list(fill_progress_events)
                        fill_progress_events.clear()
                    for snapshot in pending_fill_snapshots:
                        snapshot_event = str(snapshot.get("event") or "")
                        snapshot_attempt_raw = snapshot.get("attempt")
                        if isinstance(snapshot_attempt_raw, int):
                            snapshot_attempt = snapshot_attempt_raw
                        else:
                            try:
                                snapshot_attempt = (
                                    int(snapshot_attempt_raw) if snapshot_attempt_raw is not None else 0
                                )
                            except Exception:
                                snapshot_attempt = 0
                        snapshot_chapters = snapshot.get("chapters_snapshot")
                        snapshot_marker = (snapshot_event, snapshot_attempt)
                        if (
                            snapshot_event in (
                                "attempt_applied",
                                "gap_repair_applied",
                                "gap_repair_final_sweep_applied",
                            )
                            and snapshot_marker != last_snapshot_marker
                            and isinstance(snapshot_chapters, list)
                        ):
                            yield sse_result({"outline_md": preview_outline_md, "chapters": snapshot_chapters})
                            last_snapshot_marker = snapshot_marker
                        message = outline_route._outline_fill_progress_message(snapshot)
                        if message != last_message:
                            yield sse_progress(message=message, progress=94)
                            last_message = message
                    if fill_future.done():
                        break
                    time.sleep(outline_route.OUTLINE_FILL_POLL_INTERVAL_SECONDS)

                data, fill_warnings, fill_run_ids = fill_future.result()
            warnings.extend(fill_warnings)
            if fill_run_ids:
                coverage = data.get("chapter_coverage")
                if isinstance(coverage, dict):
                    coverage["fill_run_ids"] = fill_run_ids
                    data["chapter_coverage"] = coverage

        warnings = outline_route._dedupe_warnings(warnings)
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
        if generation_run_id is not None:
            data["generation_run_id"] = generation_run_id

        result_data = dict(data)
        result_data.pop("raw_output", None)
        result_data.pop("raw_json", None)
        result_data.pop("fixed_json", None)

        yield sse_progress(message="完成", progress=100, status="success")
        yield sse_result(result_data)
        yield sse_done()
    except GeneratorExit:
        return
    except AppError as exc:
        if not stream_run_written:
            write_generation_run(
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                chapter_id=None,
                run_type="outline_stream",
                provider=llm_call.provider,
                model=llm_call.model,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                prompt_render_log_json=prompt_render_log_json,
                params_json=run_params_json,
                output_text=raw_output or None,
                error_json=json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False),
            )
        yield sse_error(error=f"{exc.message} ({exc.code})", code=exc.status_code)
        yield sse_done()
    except Exception:
        if not stream_run_written:
            write_generation_run(
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                chapter_id=None,
                run_type="outline_stream",
                provider=llm_call.provider,
                model=llm_call.model,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                prompt_render_log_json=prompt_render_log_json,
                params_json=run_params_json,
                output_text=raw_output or None,
                error_json=json.dumps({"code": "INTERNAL_ERROR", "message": "服务器内部错误"}, ensure_ascii=False),
            )
        yield sse_error(error="服务器内部错误", code=500)
        yield sse_done()
