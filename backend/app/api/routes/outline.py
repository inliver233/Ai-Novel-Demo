from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time
from collections.abc import Callable

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.core.logging import log_event
from app.db.session import SessionLocal
from app.llm.capabilities import max_output_tokens_limit
from app.llm.client import call_llm_stream_messages
from app.models.character import Character
from app.models.llm_preset import LLMPreset
from app.models.project_settings import ProjectSettings
from app.schemas.outline_generate import OutlineGenerateRequest
from app.services.generation_service import build_run_params_json, call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.outline_store import ensure_active_outline
from app.services.output_contracts import build_repair_prompt_for_task, contract_for_task
from app.services.prompt_presets import render_preset_for_task
from app.services.prompt_store import format_characters
from app.services.run_store import write_generation_run
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.style_resolution_service import resolve_style_guide
from app.services.vector_rag_service import schedule_vector_rebuild_task
from app.utils.sse_response import (
    create_sse_response,
    sse_chunk,
    sse_done,
    sse_error,
    sse_heartbeat,
    sse_progress,
    sse_result,
)
from app.models.outline import Outline
from app.schemas.outline import OutlineOut, OutlineUpdate

router = APIRouter()
logger = logging.getLogger("ainovel")
OUTLINE_FILL_MIN_BATCH_SIZE = 6
OUTLINE_FILL_MAX_BATCH_SIZE = 18
OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT = 3
OUTLINE_FILL_MAX_TOTAL_ATTEMPTS = 48
OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS = 1.0
OUTLINE_FILL_POLL_INTERVAL_SECONDS = 0.2

OutlineFillProgressHook = Callable[[dict[str, object]], None]


def _mark_vector_index_dirty(db: DbDep, *, project_id: str) -> None:
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id)
        db.add(row)
        db.flush()
    row.vector_index_dirty = True


def _extract_target_chapter_count(requirements: dict[str, object] | None) -> int | None:
    if not isinstance(requirements, dict):
        return None
    raw = requirements.get("chapter_count")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return None
            value = int(text)
        else:
            value = int(raw)
    except Exception:
        return None
    if value <= 0:
        return None
    # Keep a sanity cap for prompt safety.
    return min(value, 2000)


def _build_outline_generation_guidance(target_chapter_count: int | None) -> dict[str, str]:
    if not target_chapter_count:
        return {
            "chapter_count_rule": "",
            "chapter_detail_rule": "beats 每章 5~9 条，按发生顺序；每条用短句，明确“发生了什么/造成什么后果”。",
        }
    if target_chapter_count <= 20:
        detail = "beats 每章 5~9 条，按发生顺序；每条用短句，明确“发生了什么/造成什么后果”。"
    elif target_chapter_count <= 40:
        detail = "beats 每章 2~4 条，保持因果推进；每条保持短句，避免冗长。"
    elif target_chapter_count <= 80:
        detail = "beats 每章 1~2 条，仅保留关键推进；优先保证章号覆盖完整。"
    elif target_chapter_count <= 120:
        detail = "beats 每章 1~2 条，只保留主冲突与关键转折，保证节奏连续。"
    else:
        detail = "beats 每章 1 条，极简表达关键推进；若长度受限，优先保留章节覆盖与编号完整。"
    return {
        "chapter_count_rule": (
            f"chapters 必须输出 {target_chapter_count} 章，number 需完整覆盖 1..{target_chapter_count} 且不缺号。"
        ),
        "chapter_detail_rule": detail,
    }


def _chapter_beats_count(chapter: dict[str, object]) -> int:
    beats_raw = chapter.get("beats")
    if not isinstance(beats_raw, list):
        return 0
    count = 0
    for beat in beats_raw:
        if isinstance(beat, str) and beat.strip():
            count += 1
    return count


def _outline_fill_detail_rule(*, target_chapter_count: int, existing_chapters: list[dict[str, object]]) -> str:
    base_rule = _build_outline_generation_guidance(target_chapter_count).get("chapter_detail_rule") or (
        "beats 每章 1~2 条，保持关键推进。"
    )

    beat_counts: list[int] = []
    for chapter in existing_chapters:
        count = _chapter_beats_count(chapter)
        if count > 0:
            beat_counts.append(count)
    beat_counts.sort()
    if not beat_counts:
        return base_rule

    median = beat_counts[len(beat_counts) // 2]
    low = max(1, median - 1)
    high = max(low, median + 1)

    if target_chapter_count > 120:
        low, high = min(low, 2), min(high, 2)
    elif target_chapter_count > 80:
        low, high = min(low, 2), min(high, 3)
    elif target_chapter_count > 40:
        low, high = min(low, 2), min(high, 4)
    else:
        low, high = min(low, 4), min(high, 6)

    consistency = (
        f"补全章节的 beats 粒度需尽量贴近已有章节（当前已生成章节 beats 中位数约 {median} 条）；"
        f"本轮建议每章 {low}~{high} 条。"
    )
    return f"{base_rule} {consistency}"


def _outline_fill_style_samples(existing_chapters: list[dict[str, object]]) -> str:
    if not existing_chapters:
        return "[]"

    total = len(existing_chapters)
    sample_indexes = sorted({0, min(1, total - 1), total // 2, total - 1})
    samples: list[dict[str, object]] = []
    for idx in sample_indexes:
        if idx < 0 or idx >= total:
            continue
        chapter = existing_chapters[idx]
        number = int(chapter.get("number") or 0)
        if number <= 0:
            continue
        title = str(chapter.get("title") or "")[:24]
        beats_raw = chapter.get("beats")
        beats: list[str] = []
        if isinstance(beats_raw, list):
            for beat in beats_raw:
                text = str(beat).strip()
                if text:
                    beats.append(text[:42])
                if len(beats) >= 3:
                    break
        samples.append({"number": number, "title": title, "beats": beats})
        if len(samples) >= 4:
            break
    return json.dumps(samples, ensure_ascii=False)


def _recommend_outline_max_tokens(
    *,
    target_chapter_count: int | None,
    provider: str,
    model: str | None,
    current_max_tokens: int | None,
) -> int | None:
    if not target_chapter_count or target_chapter_count <= 20:
        return None
    if target_chapter_count <= 40:
        wanted = 8192
    else:
        wanted = 12000

    limit = max_output_tokens_limit(provider, model)
    if isinstance(limit, int) and limit > 0:
        wanted = min(wanted, int(limit))

    if isinstance(current_max_tokens, int) and current_max_tokens >= wanted:
        return None
    return wanted if wanted > 0 else None


def _dedupe_warnings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _normalize_outline_chapters(chapters: object) -> tuple[list[dict[str, object]], list[str]]:
    if not isinstance(chapters, list):
        return [], []

    warnings: list[str] = []
    by_number: dict[int, dict[str, object]] = {}
    dropped_invalid = 0
    dropped_non_positive = 0
    deduped = 0

    for item in chapters:
        if not isinstance(item, dict):
            dropped_invalid += 1
            continue
        try:
            number = int(item.get("number"))
        except Exception:
            dropped_invalid += 1
            continue
        if number <= 0:
            dropped_non_positive += 1
            continue

        title = str(item.get("title") or "").strip()
        beats_raw = item.get("beats")
        beats: list[str] = []
        if isinstance(beats_raw, list):
            for beat in beats_raw:
                if beat is None:
                    continue
                text = str(beat).strip()
                if text:
                    beats.append(text)
        elif isinstance(beats_raw, str):
            text = beats_raw.strip()
            if text:
                beats.append(text)

        chapter = {"number": number, "title": title, "beats": beats}
        existing = by_number.get(number)
        if existing is None:
            by_number[number] = chapter
            continue

        deduped += 1
        existing_title = str(existing.get("title") or "").strip()
        existing_beats = existing.get("beats")
        existing_beats_count = len(existing_beats) if isinstance(existing_beats, list) else 0
        existing_score = len(existing_title) + existing_beats_count
        next_score = len(title) + len(beats)
        if next_score > existing_score:
            by_number[number] = chapter

    if dropped_invalid:
        warnings.append("outline_chapter_invalid_filtered")
    if dropped_non_positive:
        warnings.append("outline_chapter_non_positive_filtered")
    if deduped:
        warnings.append("outline_chapter_number_deduped")

    normalized = [by_number[n] for n in sorted(by_number.keys())]
    return normalized, warnings


def _clone_outline_chapters(chapters: list[dict[str, object]]) -> list[dict[str, object]]:
    cloned: list[dict[str, object]] = []
    for chapter in chapters:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        title = str(chapter.get("title") or "")
        beats_raw = chapter.get("beats")
        beats: list[str] = []
        if isinstance(beats_raw, list):
            for beat in beats_raw:
                text = str(beat).strip()
                if text:
                    beats.append(text)
        cloned.append({"number": number, "title": title, "beats": beats})
    return cloned


def _chapter_score(chapter: dict[str, object]) -> int:
    title = str(chapter.get("title") or "").strip()
    beats = chapter.get("beats")
    beats_count = len(beats) if isinstance(beats, list) else 0
    return len(title) + beats_count


def _collect_missing_chapter_numbers(chapters: list[dict[str, object]], target_chapter_count: int) -> list[int]:
    existing_numbers: set[int] = set()
    for chapter in chapters:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if 1 <= number <= target_chapter_count:
            existing_numbers.add(number)
    return [n for n in range(1, target_chapter_count + 1) if n not in existing_numbers]


def _format_chapter_number_ranges(numbers: list[int]) -> str:
    if not numbers:
        return ""
    nums = sorted(set(int(n) for n in numbers))
    ranges: list[str] = []
    start = nums[0]
    prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = n
        prev = n
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def _outline_fill_batch_size_for_missing(missing_count: int) -> int:
    if missing_count <= 0:
        return OUTLINE_FILL_MIN_BATCH_SIZE
    if missing_count >= 160:
        return OUTLINE_FILL_MAX_BATCH_SIZE
    if missing_count >= 80:
        return 14
    if missing_count >= 40:
        return 12
    if missing_count >= 20:
        return 10
    if missing_count >= 10:
        return 8
    return OUTLINE_FILL_MIN_BATCH_SIZE


def _outline_fill_max_attempts_for_missing(missing_count: int) -> int:
    if missing_count <= 0:
        return 1
    # Weak models may only return ~5 chapters per call; keep enough room for incremental convergence.
    estimated = (missing_count + 4) // 5 + 2
    return max(6, min(OUTLINE_FILL_MAX_TOTAL_ATTEMPTS, estimated))


def _outline_fill_progress_message(progress: dict[str, object] | None) -> str:
    if not isinstance(progress, dict):
        return "补全缺失章节..."
    remaining_raw = progress.get("remaining_count")
    remaining = int(remaining_raw) if isinstance(remaining_raw, int) else 0
    attempt_raw = progress.get("attempt")
    attempt = int(attempt_raw) if isinstance(attempt_raw, int) else 0
    max_attempts_raw = progress.get("max_attempts")
    max_attempts = int(max_attempts_raw) if isinstance(max_attempts_raw, int) else 0
    if attempt > 0 and max_attempts > 0 and remaining > 0:
        return f"补全缺失章节... 第 {attempt}/{max_attempts} 轮，剩余 {remaining} 章"
    if remaining > 0:
        return f"补全缺失章节... 剩余 {remaining} 章"
    return "补全缺失章节..."


def _enforce_outline_chapter_coverage(
    *,
    data: dict[str, object],
    target_chapter_count: int | None,
) -> tuple[dict[str, object], list[str]]:
    if not target_chapter_count or target_chapter_count <= 0:
        return data, []

    raw_chapters = data.get("chapters")
    normalized, warnings = _normalize_outline_chapters(raw_chapters)
    if not normalized:
        return data, warnings

    by_number: dict[int, dict[str, object]] = {}
    filtered_beyond_target = 0
    for chapter in normalized:
        number = int(chapter["number"])
        if number > target_chapter_count:
            filtered_beyond_target += 1
            continue
        by_number[number] = chapter

    if filtered_beyond_target:
        warnings.append("outline_chapter_beyond_target_filtered")

    chapters_out = [by_number[n] for n in sorted(by_number.keys())]
    missing_numbers = _collect_missing_chapter_numbers(chapters_out, target_chapter_count=target_chapter_count)
    coverage: dict[str, object] = {
        "target_chapter_count": target_chapter_count,
        "parsed_chapter_count": len(chapters_out),
        "missing_count": len(missing_numbers),
        "missing_numbers": missing_numbers,
    }
    if missing_numbers:
        warnings.append("outline_chapter_coverage_incomplete")
    data["chapter_coverage"] = coverage

    data["chapters"] = chapters_out
    return data, warnings


def _build_outline_missing_chapters_prompts(
    *,
    target_chapter_count: int,
    missing_numbers: list[int],
    existing_chapters: list[dict[str, object]],
    outline_md: str,
) -> tuple[str, str]:
    fill_detail_rule = _outline_fill_detail_rule(
        target_chapter_count=target_chapter_count,
        existing_chapters=existing_chapters,
    )
    style_samples = _outline_fill_style_samples(existing_chapters)
    system = (
        "你是严谨的长篇大纲补全器。"
        "你必须只输出一个 JSON 对象，禁止任何解释、Markdown、代码块。"
        '输出格式固定为：{"chapters":[{"number":int,"title":string,"beats":[string]}]}。'
        "仅输出请求的缺失章号，每个章号出现且仅出现一次。"
        "禁止输出‘待补全/自动补齐/占位/TODO’等占位词。"
        "每个 beats 必须是具体事件，避免空泛总结。"
    )
    compact = [{"number": int(c["number"]), "title": str(c.get("title") or "")[:24]} for c in existing_chapters if "number" in c]
    if len(compact) > 60:
        compact = [*compact[:30], *compact[-30:]]
    user = (
        f"目标总章数：{target_chapter_count}\n"
        f"缺失章号：{_format_chapter_number_ranges(missing_numbers)}\n"
        f"已有章节（仅供连续性参考，不可重写）：{json.dumps(compact, ensure_ascii=False)}\n"
        f"风格参考样本（模仿细节密度与句式，不得复用剧情）：{style_samples}\n"
        f"整体梗概（节选）：{(outline_md or '')[:2500]}\n\n"
        "请只输出缺失章号对应的 chapters。\n"
        f"每章要求：title 简洁；{fill_detail_rule}"
    )
    return system, user


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
    if not target_chapter_count or target_chapter_count <= 0:
        return data, [], []
    chapters_now, normalize_warnings = _normalize_outline_chapters(data.get("chapters"))
    if not chapters_now:
        return data, normalize_warnings, []

    warnings: list[str] = list(normalize_warnings)
    continue_run_ids: list[str] = []
    contract = contract_for_task("outline_generate")
    missing_numbers = _collect_missing_chapter_numbers(chapters_now, target_chapter_count=target_chapter_count)
    max_attempts = _outline_fill_max_attempts_for_missing(len(missing_numbers))
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
        missing_numbers = _collect_missing_chapter_numbers(chapters_now, target_chapter_count=target_chapter_count)
        if not missing_numbers:
            break
        batch_size = _outline_fill_batch_size_for_missing(len(missing_numbers))
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
        fill_system, fill_user = _build_outline_missing_chapters_prompts(
            target_chapter_count=target_chapter_count,
            missing_numbers=batch_missing,
            existing_chapters=chapters_now,
            outline_md=str(data.get("outline_md") or ""),
        )
        current_max_tokens = llm_call.params.get("max_tokens")
        current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
        fill_max_tokens = _recommend_outline_max_tokens(
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
            if stagnant_rounds >= OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue
        continue_run_ids.append(filled.run_id)
        filled_parsed = contract.parse(filled.text, finish_reason=filled.finish_reason)
        filled_data, filled_warnings, filled_error = filled_parsed.data, filled_parsed.warnings, filled_parsed.parse_error
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
                    }
                )
            if stagnant_rounds >= OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue

        incoming, incoming_warnings = _normalize_outline_chapters(filled_data.get("chapters"))
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
            if stagnant_rounds >= OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue

        accepted = 0
        accepted_numbers: list[int] = []
        allowed = set(batch_missing)
        by_number = {int(c["number"]): c for c in chapters_now if int(c["number"]) <= target_chapter_count}
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
            if _chapter_score(chapter) > _chapter_score(previous):
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
            if stagnant_rounds >= OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT:
                break
            continue

        warnings.append("outline_fill_missing_applied")
        stagnant_rounds = 0
        chapters_now = [by_number[n] for n in sorted(by_number.keys())]
        remaining = len(_collect_missing_chapter_numbers(chapters_now, target_chapter_count=target_chapter_count))
        if progress_hook is not None:
            chapter_snapshot = _clone_outline_chapters(chapters_now)
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
                }
            )

    data["chapters"] = chapters_now
    data, coverage_warnings = _enforce_outline_chapter_coverage(data=data, target_chapter_count=target_chapter_count)
    warnings.extend(coverage_warnings)
    coverage = data.get("chapter_coverage")
    if isinstance(coverage, dict):
        remaining_count = int(coverage.get("missing_count") or 0)
        if remaining_count > 0:
            warnings.append("outline_fill_missing_remaining")
    else:
        remaining_count = 0
    if progress_hook is not None:
        progress_hook(
            {
                "event": "fill_done",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "remaining_count": remaining_count,
            }
        )
    return data, _dedupe_warnings(warnings), continue_run_ids


@router.get("/projects/{project_id}/outline")
def get_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    project = require_project_viewer(db, project_id=project_id, user_id=user_id)
    row = db.get(Outline, project.active_outline_id) if project.active_outline_id else None
    if row is None:
        row = (
            db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.updated_at.desc()).limit(1))
            .scalars()
            .first()
        )
    if row is None:
        row = ensure_active_outline(db, project=project)
    structure = None
    if row.structure_json:
        try:
            structure = json.loads(row.structure_json)
        except Exception:
            structure = None
    payload = OutlineOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=row.content_md or "",
        structure=structure,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()
    return ok_payload(request_id=request_id, data={"outline": payload})


@router.put("/projects/{project_id}/outline")
def put_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: OutlineUpdate) -> dict:
    request_id = request.state.request_id
    project = require_project_editor(db, project_id=project_id, user_id=user_id)
    row = ensure_active_outline(db, project=project)

    if body.title is not None:
        row.title = body.title
    if body.content_md is not None:
        row.content_md = body.content_md
    if body.structure is not None:
        row.structure_json = json.dumps(body.structure, ensure_ascii=False)

    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="outline_update")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="outline_update")
    structure = None
    if row.structure_json:
        try:
            structure = json.loads(row.structure_json)
        except Exception:
            structure = None
    payload = OutlineOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=row.content_md or "",
        structure=structure,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()
    return ok_payload(request_id=request_id, data={"outline": payload})


@router.post("/projects/{project_id}/outline/generate")
def generate_outline(
    request: Request,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    resolved_api_key = ""

    prompt_system = ""
    prompt_user = ""
    prompt_render_log_json: str | None = None
    llm_call = None
    target_chapter_count: int | None = None
    run_params_extra_json: dict[str, object] = {}

    db = SessionLocal()
    try:
        project = require_project_editor(db, project_id=project_id, user_id=user_id)
        preset = db.get(LLMPreset, project_id)
        if preset is None:
            raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
        if x_llm_api_key and x_llm_provider and preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)
        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=x_llm_api_key)

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

        run_params_extra_json = {"style_resolution": style_resolution}

        chars: list[Character] = []
        if body.context.include_characters:
            chars = db.execute(select(Character).where(Character.project_id == project_id)).scalars().all()
        characters_text = format_characters(chars)
        target_chapter_count = _extract_target_chapter_count(body.requirements)
        guidance = _build_outline_generation_guidance(target_chapter_count)

        requirements_text = json.dumps(body.requirements or {}, ensure_ascii=False, indent=2)

        values = {
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
            provider=preset.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)

        llm_call = prepare_llm_call(preset)
        current_max_tokens = llm_call.params.get("max_tokens")
        current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
        wanted_max_tokens = _recommend_outline_max_tokens(
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
    finally:
        db.close()

    if llm_call is None:
        raise AppError(code="INTERNAL_ERROR", message="LLM 调用准备失败", status_code=500)

    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=None,
        run_type="outline",
        api_key=str(resolved_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
        llm_call=llm_call,
        run_params_extra_json=run_params_extra_json,
    )

    raw_output = llm_result.text
    finish_reason = llm_result.finish_reason
    contract = contract_for_task("outline_generate")
    parsed = contract.parse(raw_output, finish_reason=finish_reason)
    data, warnings, parse_error = parsed.data, parsed.warnings, parsed.parse_error

    if parse_error is not None and llm_call.provider in (
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
            fix_call = with_param_overrides(llm_call, {"temperature": 0, "max_tokens": 1024})
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
            fixed_data, fixed_warnings, fixed_error = fixed_parsed.data, fixed_parsed.warnings, fixed_parsed.parse_error
            if fixed_error is None and fixed_data.get("chapters"):
                fixed_data["raw_output"] = raw_output
                fixed_data["fixed_json"] = fixed_data.get("raw_json") or fixed.text
                data = fixed_data
                warnings.extend(["json_fixed_via_llm", *fixed_warnings])
                parse_error = None
        except AppError:
            warnings.append("outline_fix_json_failed")

    if parse_error is None:
        data, coverage_warnings = _enforce_outline_chapter_coverage(
            data=data,
            target_chapter_count=target_chapter_count,
        )
        warnings.extend(coverage_warnings)
        data, fill_warnings, fill_run_ids = _fill_outline_missing_chapters_with_llm(
            data=data,
            target_chapter_count=target_chapter_count,
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            api_key=str(resolved_api_key),
            llm_call=llm_call,
            run_params_extra_json=run_params_extra_json,
        )
        warnings.extend(fill_warnings)
        if fill_run_ids:
            coverage = data.get("chapter_coverage")
            if isinstance(coverage, dict):
                coverage["fill_run_ids"] = fill_run_ids
                data["chapter_coverage"] = coverage

    warnings = _dedupe_warnings(warnings)
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
    return ok_payload(request_id=request_id, data=data)


@router.post("/projects/{project_id}/outline/generate-stream")
def generate_outline_stream(
    request: Request,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
):
    request_id = request.state.request_id

    def event_generator():
        yield sse_progress(message="准备生成...", progress=0)

        prompt_system = ""
        prompt_user = ""
        prompt_render_log_json: str | None = None
        run_params_extra_json: dict[str, object] | None = None
        run_params_json: str | None = None
        llm_call = None
        resolved_api_key = ""
        target_chapter_count: int | None = None

        db = SessionLocal()
        try:
            project = require_project_editor(db, project_id=project_id, user_id=user_id)
            preset = db.get(LLMPreset, project_id)
            if preset is None:
                raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
            if x_llm_api_key and x_llm_provider and preset.provider != x_llm_provider:
                raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)
            resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=x_llm_api_key)

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

            run_params_extra_json = {"style_resolution": style_resolution}

            chars: list[Character] = []
            if body.context.include_characters:
                chars = db.execute(select(Character).where(Character.project_id == project_id)).scalars().all()
            characters_text = format_characters(chars)
            target_chapter_count = _extract_target_chapter_count(body.requirements)
            guidance = _build_outline_generation_guidance(target_chapter_count)

            requirements_text = json.dumps(body.requirements or {}, ensure_ascii=False, indent=2)
            values = {
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
                provider=preset.provider,
            )
            prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)
            llm_call = prepare_llm_call(preset)
            current_max_tokens = llm_call.params.get("max_tokens")
            current_max_tokens_int = int(current_max_tokens) if isinstance(current_max_tokens, int) else None
            wanted_max_tokens = _recommend_outline_max_tokens(
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
        if run_params_json is None:
            run_params_json = build_run_params_json(
                params_json=llm_call.params_json,
                memory_retrieval_log_json=None,
                extra_json=run_params_extra_json,
            )

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
                    fixed_data, fixed_warnings, fixed_error = fixed_parsed.data, fixed_parsed.warnings, fixed_parsed.parse_error
                    if fixed_error is None and fixed_data.get("chapters"):
                        fixed_data["raw_output"] = raw_output
                        fixed_data["fixed_json"] = fixed_data.get("raw_json") or fixed.text
                        data = fixed_data
                        warnings.extend(["json_fixed_via_llm", *fixed_warnings])
                        parse_error = None
                except AppError:
                    warnings.append("outline_fix_json_failed")

            if parse_error is None:
                data, coverage_warnings = _enforce_outline_chapter_coverage(
                    data=data,
                    target_chapter_count=target_chapter_count,
                )
                warnings.extend(coverage_warnings)
                preview_outline_md = str(data.get("outline_md") or "")
                preview_chapters, _preview_warnings = _normalize_outline_chapters(data.get("chapters"))
                if preview_chapters:
                    yield sse_result({"outline_md": preview_outline_md, "chapters": _clone_outline_chapters(preview_chapters)})
                if target_chapter_count:
                    yield sse_progress(message="补全缺失章节...", progress=94)
                fill_progress_lock = threading.Lock()
                fill_progress: dict[str, object] = {}

                def _on_fill_progress(update: dict[str, object]) -> None:
                    if not isinstance(update, dict):
                        return
                    with fill_progress_lock:
                        fill_progress.update(update)

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
                    last_snapshot_attempt = -1
                    while not fill_future.done():
                        now = time.monotonic()
                        if now - last_ping >= OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS:
                            yield sse_heartbeat()
                            with fill_progress_lock:
                                snapshot = dict(fill_progress)
                            snapshot_event = str(snapshot.get("event") or "")
                            snapshot_attempt_raw = snapshot.get("attempt")
                            if isinstance(snapshot_attempt_raw, int):
                                snapshot_attempt = snapshot_attempt_raw
                            else:
                                try:
                                    snapshot_attempt = int(snapshot_attempt_raw) if snapshot_attempt_raw is not None else 0
                                except Exception:
                                    snapshot_attempt = 0
                            snapshot_chapters = snapshot.get("chapters_snapshot")
                            if (
                                snapshot_event == "attempt_applied"
                                and snapshot_attempt > last_snapshot_attempt
                                and isinstance(snapshot_chapters, list)
                            ):
                                yield sse_result({"outline_md": preview_outline_md, "chapters": snapshot_chapters})
                                last_snapshot_attempt = snapshot_attempt
                            message = _outline_fill_progress_message(snapshot)
                            if message != last_message:
                                yield sse_progress(message=message, progress=94)
                                last_message = message
                            last_ping = now
                        time.sleep(OUTLINE_FILL_POLL_INTERVAL_SECONDS)

                    data, fill_warnings, fill_run_ids = fill_future.result()
                warnings.extend(fill_warnings)
                if fill_run_ids:
                    coverage = data.get("chapter_coverage")
                    if isinstance(coverage, dict):
                        coverage["fill_run_ids"] = fill_run_ids
                        data["chapter_coverage"] = coverage

            warnings = _dedupe_warnings(warnings)
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

            # Keep stream result payload compact to reduce client-side SSE parse failures on large outputs.
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
            if (
                llm_call is not None
                and not stream_run_written
            ):
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
                stream_run_written = True
            yield sse_error(error=f"{exc.message} ({exc.code})", code=exc.status_code)
            yield sse_done()
        except Exception:
            if llm_call is not None and not stream_run_written:
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
                stream_run_written = True
            yield sse_error(error="服务器内部错误", code=500)
            yield sse_done()

    return create_sse_response(event_generator())
