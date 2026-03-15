from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.llm.capabilities import max_output_tokens_limit
from app.models.project_settings import ProjectSettings
from app.schemas.outline_generate import OutlineGenerateRequest
from app.services.outline_generation_app_service import (
    generate_outline as generate_outline_service,
    generate_outline_stream_events,
    prepare_outline_stream_request,
)
from app.services.outline_store import ensure_active_outline
from app.services.output_parsers import extract_json_value, likely_truncated_json
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task
from app.utils.sse_response import create_sse_response
from app.models.outline import Outline
from app.schemas.outline import OutlineOut, OutlineUpdate
from app.services.outline_payload_normalizer import normalize_outline_content_and_structure, parse_outline_structure_json

router = APIRouter()
logger = logging.getLogger("ainovel")
OUTLINE_FILL_MIN_BATCH_SIZE = 6
OUTLINE_FILL_MAX_BATCH_SIZE = 18
OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT = 3
OUTLINE_FILL_MAX_TOTAL_ATTEMPTS = 48
OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS = 1.0
OUTLINE_FILL_POLL_INTERVAL_SECONDS = 0.2
OUTLINE_GAP_REPAIR_MAX_MISSING = 120
OUTLINE_GAP_REPAIR_BATCH_SIZE = 4
OUTLINE_GAP_REPAIR_STAGNANT_LIMIT = 4
OUTLINE_GAP_REPAIR_FINAL_SWEEP_MAX_MISSING = 36
OUTLINE_GAP_REPAIR_FINAL_SWEEP_ATTEMPTS_PER_CHAPTER = 3
OUTLINE_SEGMENT_TRIGGER_CHAPTER_COUNT = 80
OUTLINE_SEGMENT_MIN_BATCH_SIZE = 6
OUTLINE_SEGMENT_MAX_BATCH_SIZE = 12
OUTLINE_SEGMENT_DEFAULT_BATCH_SIZE = 10
OUTLINE_SEGMENT_MAX_ATTEMPTS_PER_BATCH = 6
OUTLINE_SEGMENT_STAGNANT_ATTEMPTS_LIMIT = 3
OUTLINE_SEGMENT_RECENT_CONTEXT_WINDOW = 24
OUTLINE_SEGMENT_INDEX_MAX_ITEMS = 140
OUTLINE_SEGMENT_INDEX_MAX_CHARS = 6000
OUTLINE_SEGMENT_RECENT_WINDOW_MAX_CHARS = 2800
OUTLINE_STREAM_RAW_PREVIEW_MAX_CHARS = 1800

OutlineFillProgressHook = Callable[[dict[str, object]], None]
OutlineSegmentProgressHook = Callable[[dict[str, object]], None]


def _outline_out(row: Outline) -> dict[str, object]:
    parsed_structure = parse_outline_structure_json(row.structure_json)
    content_md, structure, _ = normalize_outline_content_and_structure(content_md=row.content_md or "", structure=parsed_structure)
    return OutlineOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=content_md,
        structure=structure,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


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


def _should_use_outline_segmented_mode(target_chapter_count: int | None) -> bool:
    return bool(target_chapter_count and target_chapter_count >= OUTLINE_SEGMENT_TRIGGER_CHAPTER_COUNT)


def _outline_segment_batch_size_for_target(target_chapter_count: int) -> int:
    if target_chapter_count <= 120:
        return OUTLINE_SEGMENT_MAX_BATCH_SIZE
    if target_chapter_count <= 500:
        return OUTLINE_SEGMENT_DEFAULT_BATCH_SIZE
    return max(OUTLINE_SEGMENT_MIN_BATCH_SIZE, OUTLINE_SEGMENT_DEFAULT_BATCH_SIZE - 2)


def _outline_segment_max_attempts_for_batch(requested_count: int) -> int:
    if requested_count <= 0:
        return 1
    estimated = max(3, ((requested_count + 2) // 3) + 1)
    return min(OUTLINE_SEGMENT_MAX_ATTEMPTS_PER_BATCH, estimated)


def _outline_segment_batches(target_chapter_count: int, batch_size: int) -> list[list[int]]:
    size = max(OUTLINE_SEGMENT_MIN_BATCH_SIZE, min(OUTLINE_SEGMENT_MAX_BATCH_SIZE, int(batch_size)))
    out: list[list[int]] = []
    start = 1
    while start <= target_chapter_count:
        end = min(target_chapter_count, start + size - 1)
        out.append(list(range(start, end + 1)))
        start = end + 1
    return out


def _shrink_outline_segment_items(
    items: list[dict[str, object]],
    *,
    max_items: int,
    max_chars: int,
) -> list[dict[str, object]]:
    if not items:
        return []
    sampled = list(items)
    if len(sampled) > max_items:
        head = max(20, max_items // 2)
        tail = max_items - head
        sampled = [*sampled[:head], *sampled[-tail:]]

    payload = json.dumps({"items": sampled}, ensure_ascii=False)
    if len(payload) <= max_chars:
        return sampled

    compact = list(sampled)
    while len(compact) > 32:
        compact = [*compact[: len(compact) // 2], *compact[-max(1, len(compact) // 4) :]]
        payload = json.dumps({"items": compact}, ensure_ascii=False)
        if len(payload) <= max_chars:
            return compact
    return compact


def _strip_segment_conflicting_prompt_sections(text: str) -> str:
    if not text.strip():
        return text
    # Segmented mode should not retain "single response must cover all chapters" instructions.
    without_target = re.sub(r"(?is)<\s*CHAPTER_TARGET\s*>[\s\S]*?<\s*/\s*CHAPTER_TARGET\s*>", "", text)
    return without_target.strip()


def _build_outline_segment_chapter_index(chapters: list[dict[str, object]]) -> str:
    items: list[dict[str, object]] = []
    for chapter in chapters:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if number <= 0:
            continue
        title = str(chapter.get("title") or "").strip()
        items.append({"number": number, "title": title[:28]})
    items.sort(key=lambda row: int(row.get("number") or 0))
    total = len(items)
    sampled = _shrink_outline_segment_items(
        items,
        max_items=OUTLINE_SEGMENT_INDEX_MAX_ITEMS,
        max_chars=OUTLINE_SEGMENT_INDEX_MAX_CHARS,
    )
    payload: dict[str, object] = {"total": total, "items": sampled}
    omitted = total - len(sampled)
    if omitted > 0:
        payload["omitted"] = omitted
    return json.dumps(payload, ensure_ascii=False)


def _build_outline_segment_recent_window(chapters: list[dict[str, object]]) -> str:
    if not chapters:
        return "[]"
    window = chapters[-OUTLINE_SEGMENT_RECENT_CONTEXT_WINDOW:]
    items: list[dict[str, object]] = []
    for chapter in window:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if number <= 0:
            continue
        title = str(chapter.get("title") or "").strip()
        beats_raw = chapter.get("beats")
        beats: list[str] = []
        if isinstance(beats_raw, list):
            for beat in beats_raw:
                text = str(beat).strip()
                if text:
                    beats.append(text[:64])
                if len(beats) >= 3:
                    break
        items.append({"number": number, "title": title[:28], "beats": beats})
    text = json.dumps(items, ensure_ascii=False)
    if len(text) <= OUTLINE_SEGMENT_RECENT_WINDOW_MAX_CHARS:
        return text
    compact: list[dict[str, object]] = []
    for row in items:
        compact.append(
            {
                "number": int(row.get("number") or 0),
                "title": str(row.get("title") or "")[:18],
                "beats": [str(x)[:40] for x in (row.get("beats") if isinstance(row.get("beats"), list) else [])[:2]],
            }
        )
    return json.dumps(compact, ensure_ascii=False)


def _recommend_outline_segment_max_tokens(
    *,
    requested_count: int,
    provider: str,
    model: str | None,
    current_max_tokens: int | None,
) -> int | None:
    if requested_count <= 0:
        return None
    wanted = max(1800, min(4200, 1200 + requested_count * 230))
    limit = max_output_tokens_limit(provider, model)
    if isinstance(limit, int) and limit > 0:
        wanted = min(wanted, int(limit))
    if isinstance(current_max_tokens, int) and current_max_tokens >= wanted:
        return None
    return wanted if wanted > 0 else None


def _build_outline_stream_raw_preview(
    text: object,
    *,
    max_chars: int = OUTLINE_STREAM_RAW_PREVIEW_MAX_CHARS,
) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    omitted = len(cleaned) - max_chars
    return f"{cleaned[:max_chars]}\n...(已截断 {omitted} 字符)"


def _parse_outline_batch_output(
    *,
    text: str,
    finish_reason: str | None = None,
    fallback_outline_md: str | None = None,
) -> tuple[dict[str, object], list[str], dict[str, object] | None]:
    warnings: list[str] = []
    value, raw_json = extract_json_value(text)
    if not isinstance(value, dict):
        parse_error: dict[str, object] = {"code": "OUTLINE_PARSE_ERROR", "message": "无法从模型输出解析章节结构"}
        if finish_reason == "length" or likely_truncated_json(text):
            parse_error["hint"] = "输出疑似被截断（JSON 未闭合），将自动重试当前分段"
        data = {"outline_md": str(fallback_outline_md or ""), "chapters": [], "raw_output": text}
        return data, warnings, parse_error

    outline_md_raw = value.get("outline_md")
    outline_md = outline_md_raw.strip() if isinstance(outline_md_raw, str) else ""
    if not outline_md and isinstance(fallback_outline_md, str):
        outline_md = fallback_outline_md.strip()

    chapters_out, chapter_warnings = _normalize_outline_chapters(value.get("chapters"))
    warnings.extend(chapter_warnings)
    if finish_reason == "length":
        warnings.append("output_truncated")

    data: dict[str, object] = {"outline_md": outline_md, "chapters": chapters_out, "raw_output": text}
    if raw_json:
        data["raw_json"] = raw_json
    if chapters_out:
        return data, warnings, None

    parse_error = {"code": "OUTLINE_PARSE_ERROR", "message": "无法从模型输出解析章节结构"}
    if finish_reason == "length" or likely_truncated_json(text):
        parse_error["hint"] = "输出疑似被截断（JSON 未闭合），将自动重试当前分段"
    return data, warnings, parse_error


def _build_outline_segment_prompts(
    *,
    base_prompt_system: str,
    base_prompt_user: str,
    target_chapter_count: int,
    batch_numbers: list[int],
    existing_chapters: list[dict[str, object]],
    existing_outline_md: str,
    attempt: int,
    max_attempts: int,
    previous_output_numbers: list[int] | None = None,
    previous_failure_reason: str | None = None,
) -> tuple[str, str]:
    base_user = _strip_segment_conflicting_prompt_sections(base_prompt_user)
    missing_ranges = _format_chapter_number_ranges(batch_numbers)
    missing_numbers_json = json.dumps(batch_numbers, ensure_ascii=False)
    detail_rule = _outline_fill_detail_rule(
        target_chapter_count=target_chapter_count,
        existing_chapters=existing_chapters,
    )
    existing_numbers_set: set[int] = set()
    for chapter in existing_chapters:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if number > 0:
            existing_numbers_set.add(number)
    existing_numbers = sorted(existing_numbers_set)
    existing_ranges = _format_chapter_number_ranges(existing_numbers)
    chapter_index = _build_outline_segment_chapter_index(existing_chapters)
    recent_window = _build_outline_segment_recent_window(existing_chapters)
    outline_anchor = (existing_outline_md or "").strip()
    if len(outline_anchor) > 3600:
        outline_anchor = outline_anchor[:3600]
    feedback_block = ""
    if attempt > 1:
        prev_numbers_text = _format_chapter_number_ranges(previous_output_numbers or [])
        if not prev_numbers_text:
            prev_numbers_text = "（无可识别章号）"
        failure_reason = (previous_failure_reason or "上一轮输出未满足当前批次约束").strip()
        feedback_block = (
            "<LAST_ATTEMPT_FEEDBACK>\n"
            f"上一轮失败原因：{failure_reason}\n"
            f"上一轮输出章号：{prev_numbers_text}\n"
            "本轮必须纠正：只输出当前批次章号数组对应的章节。\n"
            "</LAST_ATTEMPT_FEEDBACK>\n"
        )

    system = (
        f"{base_prompt_system}\n\n"
        "[分段生成协议]\n"
        "你现在处于“长篇章节分段生成”模式。\n"
        "你必须只输出一个 JSON 对象，禁止任何解释、Markdown、代码块。\n"
        'JSON 固定为：{"outline_md": string, "chapters":[{"number":int,"title":string,"beats":[string]}]}。\n'
        "本轮只能输出要求章号，不能输出范围外章节。\n"
        "本轮要求的每个章号必须出现且仅出现一次。\n"
        "不得输出占位内容（如 TODO/待补全/略）。\n"
    )
    user = (
        f"{base_user}\n\n"
        "<SEGMENT_TASK>\n"
        f"目标总章数：{target_chapter_count}\n"
        f"当前批次缺失章号：{missing_ranges}\n"
        f"当前批次章号数组（严格按此输出）：{missing_numbers_json}\n"
        f"已完成章号（禁止输出）：{existing_ranges or '（空）'}\n"
        f"当前尝试：第 {attempt}/{max_attempts} 轮（仅补当前批次缺失章号）\n"
        f"已生成章节标题索引（全量，不可改写）：{chapter_index}\n"
        f"最近章节细节（用于衔接语义）：{recent_window}\n"
        f"全书总纲锚点（不可改写）：{outline_anchor}\n"
        f"每章细节规则：{detail_rule}\n"
        f"{feedback_block}"
        "输出要求：\n"
        "- chapters 只能包含当前批次缺失章号，且必须全部覆盖。\n"
        "- number 必须严格等于指定章号，不得跳号/重号。\n"
        "- 若输出任何已完成章号或范围外章号，本轮会被判定失败并重试。\n"
        "- title 简洁明确，beats 使用短句、强调因果推进。\n"
        "- outline_md 可沿用既有总纲，不得输出空对象或额外字段。\n"
        "- 输出前自检：chapters.number 集合必须与当前批次章号数组完全一致。\n"
        "</SEGMENT_TASK>"
    )
    return system, user


def _outline_segment_progress_message(progress: dict[str, object] | None) -> str:
    if not isinstance(progress, dict):
        return "长篇分段生成中..."
    event = str(progress.get("event") or "")
    if event.startswith("fill_"):
        mapped = dict(progress)
        mapped["event"] = event.removeprefix("fill_")
        return _outline_fill_progress_message(mapped)

    batch_index = int(progress.get("batch_index") or 0)
    batch_count = int(progress.get("batch_count") or 0)
    range_text = str(progress.get("range") or "")
    attempt = int(progress.get("attempt") or 0)
    max_attempts = int(progress.get("max_attempts") or 0)
    completed = int(progress.get("completed_count") or 0)
    target = int(progress.get("target_chapter_count") or 0)
    remaining = int(progress.get("remaining_count") or 0)

    if event == "segment_start":
        return f"长篇分段生成启动：共 {batch_count} 批"
    if event == "batch_attempt_start":
        return f"分段生成 第 {batch_index}/{batch_count} 批（章号 {range_text}），尝试 {attempt}/{max_attempts}"
    if event == "batch_call_failed":
        return f"分段生成 第 {batch_index}/{batch_count} 批调用失败，自动重试（{attempt}/{max_attempts}）"
    if event == "batch_parse_failed":
        return f"分段生成 第 {batch_index}/{batch_count} 批解析失败，自动重试（{attempt}/{max_attempts}）"
    if event == "batch_no_progress":
        return f"分段生成 第 {batch_index}/{batch_count} 批无有效新章，自动重试（{attempt}/{max_attempts}）"
    if event == "batch_applied":
        if target > 0:
            return f"分段生成已完成 {completed}/{target} 章，剩余 {remaining} 章"
        return "分段生成已应用一批结果"
    if event == "batch_incomplete":
        return f"分段生成 第 {batch_index}/{batch_count} 批未完全收敛，剩余 {remaining} 章"
    if event == "segment_done":
        return "分段生成完成"
    if target > 0 and completed > 0:
        return f"分段生成中... 已完成 {completed}/{target} 章"
    return "长篇分段生成中..."


def _extract_outline_chapter_numbers(chapters: list[dict[str, object]], *, limit: int = 64) -> list[int]:
    numbers: set[int] = set()
    for chapter in chapters:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if number <= 0:
            continue
        numbers.add(number)
        if len(numbers) >= limit:
            break
    return sorted(numbers)


def _merge_segment_chapters(
    *,
    by_number: dict[int, dict[str, object]],
    incoming: list[dict[str, object]],
    allowed_numbers: set[int],
) -> tuple[int, list[int]]:
    accepted = 0
    accepted_numbers: list[int] = []
    for chapter in incoming:
        number = int(chapter.get("number") or 0)
        if number <= 0 or number not in allowed_numbers:
            continue
        previous = by_number.get(number)
        if previous is None:
            by_number[number] = chapter
            accepted += 1
            accepted_numbers.append(number)
            continue
        if _chapter_score(chapter) > _chapter_score(previous):
            by_number[number] = chapter
    return accepted, accepted_numbers


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


def _compact_neighbor_chapter(chapter: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(chapter, dict):
        return None
    try:
        number = int(chapter.get("number"))
    except Exception:
        return None
    if number <= 0:
        return None
    title = str(chapter.get("title") or "")[:28]
    beats_raw = chapter.get("beats")
    beats: list[str] = []
    if isinstance(beats_raw, list):
        for beat in beats_raw:
            text = str(beat).strip()
            if text:
                beats.append(text[:52])
            if len(beats) >= 2:
                break
    return {"number": number, "title": title, "beats": beats}


def _build_missing_neighbor_context(
    existing_chapters: list[dict[str, object]],
    missing_numbers: list[int],
    *,
    max_items: int = 24,
    max_chars: int = 2400,
) -> str:
    if not existing_chapters or not missing_numbers:
        return "[]"

    by_number: dict[int, dict[str, object]] = {}
    for chapter in existing_chapters:
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if number > 0:
            by_number[number] = chapter

    contexts: list[dict[str, object]] = []
    for number in sorted(set(int(n) for n in missing_numbers if int(n) > 0)):
        row: dict[str, object] = {"number": number}
        prev_compact = _compact_neighbor_chapter(by_number.get(number - 1))
        next_compact = _compact_neighbor_chapter(by_number.get(number + 1))
        if prev_compact is not None:
            row["prev"] = prev_compact
        if next_compact is not None:
            row["next"] = next_compact
        contexts.append(row)
        if len(contexts) >= max_items:
            break

    text = json.dumps(contexts, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    compact_rows: list[dict[str, object]] = []
    for row in contexts:
        slim: dict[str, object] = {"number": int(row.get("number") or 0)}
        prev_row = row.get("prev")
        if isinstance(prev_row, dict):
            slim["prev"] = {
                "number": int(prev_row.get("number") or 0),
                "title": str(prev_row.get("title") or "")[:18],
            }
        next_row = row.get("next")
        if isinstance(next_row, dict):
            slim["next"] = {
                "number": int(next_row.get("number") or 0),
                "title": str(next_row.get("title") or "")[:18],
            }
        compact_rows.append(slim)
    return json.dumps(compact_rows, ensure_ascii=False)


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
    event = str(progress.get("event") or "")
    remaining_raw = progress.get("remaining_count")
    remaining = int(remaining_raw) if isinstance(remaining_raw, int) else 0
    attempt_raw = progress.get("attempt")
    attempt = int(attempt_raw) if isinstance(attempt_raw, int) else 0
    max_attempts_raw = progress.get("max_attempts")
    max_attempts = int(max_attempts_raw) if isinstance(max_attempts_raw, int) else 0
    if event.startswith("gap_repair"):
        if event == "gap_repair_final_sweep_start":
            return f"终检兜底启动：剩余 {remaining} 章"
        if event == "gap_repair_final_sweep_attempt_start":
            return f"终检兜底中... 第 {attempt}/{max_attempts} 轮，剩余 {remaining} 章"
        if event == "gap_repair_final_sweep_applied":
            return f"终检兜底已插入，剩余 {remaining} 章"
        if event == "gap_repair_final_sweep_done":
            if remaining > 0:
                return f"终检兜底结束，仍缺 {remaining} 章"
            return "终检兜底完成，章节已齐全"
        if event == "gap_repair_start":
            return f"终检补全启动：剩余 {remaining} 章待修复"
        if event == "gap_repair_attempt_start":
            return f"终检补全中... 第 {attempt}/{max_attempts} 轮，剩余 {remaining} 章"
        if event == "gap_repair_applied":
            return f"终检补全已应用，剩余 {remaining} 章"
        if event == "gap_repair_done":
            if remaining > 0:
                return f"终检补全结束，仍缺 {remaining} 章"
            return "终检补全完成，章节已齐全"
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
    missing_numbers_json = json.dumps(sorted(set(int(n) for n in missing_numbers if int(n) > 0)), ensure_ascii=False)
    existing_numbers_set: set[int] = set()
    for chapter in existing_chapters:
        if not isinstance(chapter, dict):
            continue
        try:
            number = int(chapter.get("number"))
        except Exception:
            continue
        if number > 0:
            existing_numbers_set.add(number)
    existing_numbers = sorted(existing_numbers_set)
    existing_ranges = _format_chapter_number_ranges(existing_numbers)
    neighbor_context = _build_missing_neighbor_context(existing_chapters, missing_numbers)
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
        f"缺失章号数组（严格按此输出）：{missing_numbers_json}\n"
        f"已完成章号（禁止输出）：{existing_ranges or '（空）'}\n"
        f"已有章节（仅供连续性参考，不可重写）：{json.dumps(compact, ensure_ascii=False)}\n"
        f"缺失章节邻接上下文（prev/next，仅供衔接）：{neighbor_context}\n"
        f"风格参考样本（模仿细节密度与句式，不得复用剧情）：{style_samples}\n"
        f"整体梗概（节选）：{(outline_md or '')[:2500]}\n\n"
        "请只输出缺失章号对应的 chapters。\n"
        "输出前自检：chapters.number 集合必须与缺失章号数组完全一致。\n"
        f"每章要求：title 简洁；{fill_detail_rule}"
    )
    return system, user


def _outline_gap_repair_max_attempts(missing_count: int) -> int:
    if missing_count <= 0:
        return 1
    estimated = missing_count * 2 + 2
    return max(8, min(OUTLINE_FILL_MAX_TOTAL_ATTEMPTS, estimated))


def _build_outline_gap_repair_prompts(
    *,
    target_chapter_count: int,
    batch_missing: list[int],
    existing_chapters: list[dict[str, object]],
    outline_md: str,
    attempt: int,
    max_attempts: int,
    previous_output_numbers: list[int] | None = None,
    previous_failure_reason: str | None = None,
) -> tuple[str, str]:
    missing_sorted = sorted(set(int(n) for n in batch_missing if int(n) > 0))
    missing_json = json.dumps(missing_sorted, ensure_ascii=False)
    missing_ranges = _format_chapter_number_ranges(missing_sorted)
    index_json = _build_outline_segment_chapter_index(existing_chapters)
    neighbor_context = _build_missing_neighbor_context(existing_chapters, missing_sorted, max_items=12, max_chars=1800)
    style_samples = _outline_fill_style_samples(existing_chapters)
    detail_rule = _outline_fill_detail_rule(target_chapter_count=target_chapter_count, existing_chapters=existing_chapters)
    feedback_block = ""
    if attempt > 1:
        prev_numbers_text = _format_chapter_number_ranges(previous_output_numbers or [])
        if not prev_numbers_text:
            prev_numbers_text = "（无可识别章号）"
        reason = (previous_failure_reason or "上一轮未产生可采纳章节").strip()
        feedback_block = (
            "<LAST_ATTEMPT_FEEDBACK>\n"
            f"上一轮失败原因：{reason}\n"
            f"上一轮输出章号：{prev_numbers_text}\n"
            "本轮必须只输出当前批次缺失章号数组。\n"
            "</LAST_ATTEMPT_FEEDBACK>\n"
        )

    system = (
        "你是长篇大纲终检补全器。"
        "你必须只输出一个 JSON 对象，禁止任何解释、Markdown、代码块。"
        '输出格式固定为：{"chapters":[{"number":int,"title":string,"beats":[string]}]}。'
        "本轮只能输出要求章号，每个章号出现且仅出现一次。"
        "禁止输出范围外章号、禁止输出空 beats、禁止占位词。"
    )
    user = (
        f"目标总章数：{target_chapter_count}\n"
        f"本轮缺失章号：{missing_ranges}\n"
        f"本轮缺失章号数组（严格按此输出）：{missing_json}\n"
        f"全量章节索引（不可改写）：{index_json}\n"
        f"缺失章节邻接上下文（prev/next）：{neighbor_context}\n"
        f"风格参考样本：{style_samples}\n"
        f"整体梗概（节选）：{(outline_md or '')[:2400]}\n"
        f"当前尝试：第 {attempt}/{max_attempts} 轮\n"
        f"{feedback_block}"
        "输出前自检：chapters.number 集合必须与本轮缺失章号数组完全一致。\n"
        f"每章要求：title 简洁；{detail_rule}"
    )
    return system, user


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
    payload = _outline_out(row)
    return ok_payload(request_id=request_id, data={"outline": payload})


@router.put("/projects/{project_id}/outline")
def put_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: OutlineUpdate) -> dict:
    request_id = request.state.request_id
    project = require_project_editor(db, project_id=project_id, user_id=user_id)
    row = ensure_active_outline(db, project=project)

    if body.title is not None:
        row.title = body.title
    if body.content_md is not None:
        content_md, structure, normalized = normalize_outline_content_and_structure(
            content_md=body.content_md,
            structure=body.structure,
        )
        row.content_md = content_md
        if body.structure is not None or normalized:
            row.structure_json = json.dumps(structure, ensure_ascii=False) if structure is not None else None
    elif body.structure is not None:
        row.structure_json = json.dumps(body.structure, ensure_ascii=False)

    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="outline_update")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="outline_update")
    payload = _outline_out(row)
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
    data = generate_outline_service(
        request_id=request_id,
        project_id=project_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
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
    prepared = prepare_outline_stream_request(
        project_id=project_id,
        body=body,
        user_id=user_id,
        request_id=request_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    return create_sse_response(
        generate_outline_stream_events(
            request_id=request_id,
            project_id=project_id,
            body=body,
            user_id=user_id,
            prepared=prepared,
        )
    )
