from __future__ import annotations

import json
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.character import Character
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.schemas.chapter_generate import ChapterGenerateContext, ChapterGenerateRequest
from app.services.prompt_store import format_characters

PREVIOUS_CHAPTER_ENDING_CHARS = 1000
CURRENT_DRAFT_TAIL_CHARS = 1200

SMART_CONTEXT_RECENT_SUMMARIES_MAX = 20
SMART_CONTEXT_RECENT_FULL_MAX = 2
SMART_CONTEXT_RECENT_FULL_HEAD_CHARS = 1200
SMART_CONTEXT_RECENT_FULL_TAIL_CHARS = 1200
SMART_CONTEXT_SKELETON_STRIDE_SMALL = 10
SMART_CONTEXT_SKELETON_STRIDE_LARGE = 20
SMART_CONTEXT_SKELETON_LARGE_THRESHOLD = 80


def build_smart_context(
    db: Session,
    *,
    project_id: str,
    outline_id: str,
    chapter_number: int,
) -> tuple[str, str, str]:
    if chapter_number <= 1:
        return "", "", ""

    summary_rows = db.execute(
        select(Chapter.number, Chapter.title, Chapter.summary)
        .where(
            Chapter.project_id == project_id,
            Chapter.outline_id == outline_id,
            Chapter.number < chapter_number,
        )
        .order_by(Chapter.number.desc())
        .limit(SMART_CONTEXT_RECENT_SUMMARIES_MAX)
    ).all()
    summary_rows.reverse()
    recent_summary_lines: list[str] = []
    for num, title, summary in summary_rows:
        text = (summary or "").strip()
        if not text:
            continue
        title_str = (title or "").strip()
        head = f"第{num}章 {title_str}" if title_str else f"第{num}章"
        recent_summary_lines.append(f"- {head}：{text}")
    recent_summaries = "\n".join(recent_summary_lines).strip()

    full_rows = db.execute(
        select(Chapter.number, Chapter.title, Chapter.content_md)
        .where(
            Chapter.project_id == project_id,
            Chapter.outline_id == outline_id,
            Chapter.number < chapter_number,
        )
        .order_by(Chapter.number.desc())
        .limit(SMART_CONTEXT_RECENT_FULL_MAX)
    ).all()
    full_rows.reverse()
    recent_full_parts: list[str] = []
    for num, title, content_md in full_rows:
        raw = (content_md or "").strip()
        if not raw:
            continue
        title_str = (title or "").strip()
        head = f"第{num}章 {title_str}" if title_str else f"第{num}章"
        if len(raw) <= SMART_CONTEXT_RECENT_FULL_HEAD_CHARS + SMART_CONTEXT_RECENT_FULL_TAIL_CHARS + 80:
            snippet = raw
        else:
            snippet = (
                raw[:SMART_CONTEXT_RECENT_FULL_HEAD_CHARS].rstrip()
                + "\n...\n"
                + raw[-SMART_CONTEXT_RECENT_FULL_TAIL_CHARS :].lstrip()
            )
        recent_full_parts.append(f"【{head} 正文节选】\n{snippet}")
    recent_full = "\n\n".join(recent_full_parts).strip()

    total_prev = max(0, chapter_number - 1)
    stride = (
        SMART_CONTEXT_SKELETON_STRIDE_LARGE
        if total_prev >= SMART_CONTEXT_SKELETON_LARGE_THRESHOLD
        else SMART_CONTEXT_SKELETON_STRIDE_SMALL
    )
    skeleton_numbers = [n for n in range(1, chapter_number, stride)]

    skeleton = ""
    if len(skeleton_numbers) >= 2:
        skeleton_rows = db.execute(
            select(Chapter.number, Chapter.title, Chapter.summary, Chapter.plan)
            .where(
                Chapter.project_id == project_id,
                Chapter.outline_id == outline_id,
                Chapter.number.in_(skeleton_numbers),
            )
            .order_by(Chapter.number.asc())
        ).all()
        skeleton_lines: list[str] = []
        for num, title, summary, plan in skeleton_rows:
            text = (summary or "").strip() or (plan or "").strip()
            if not text:
                continue
            title_str = (title or "").strip()
            head = f"第{num}章 {title_str}" if title_str else f"第{num}章"
            skeleton_lines.append(f"- {head}：{text}")
        skeleton = "\n".join(skeleton_lines).strip()

    return recent_summaries, recent_full, skeleton


def load_previous_chapter_context(
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


def resolve_current_draft_tail(*, chapter: Chapter, request_tail: str | None) -> str:
    if request_tail is not None and request_tail.strip():
        return request_tail.strip()[-CURRENT_DRAFT_TAIL_CHARS:].lstrip()
    raw = (chapter.content_md or "").strip()
    if not raw:
        return ""
    return raw[-CURRENT_DRAFT_TAIL_CHARS:].lstrip()


def _load_project_story_text_context(
    db: Session,
    *,
    project_id: str,
    outline_id: str,
    ctx: ChapterGenerateContext,
) -> tuple[str, str, str, str, str]:
    settings_row = db.get(ProjectSettings, project_id)
    outline_row = db.get(Outline, outline_id)

    world_setting = (settings_row.world_setting if settings_row else "") or ""
    style_guide = (settings_row.style_guide if settings_row else "") or ""
    constraints = (settings_row.constraints if settings_row else "") or ""

    if not ctx.include_world_setting:
        world_setting = ""
    if not ctx.include_style_guide:
        style_guide = ""
    if not ctx.include_constraints:
        constraints = ""

    outline_text = (outline_row.content_md if outline_row else "") or ""
    if not ctx.include_outline:
        outline_text = ""

    chars: list[Character] = []
    if ctx.character_ids:
        chars = (
            db.execute(
                select(Character).where(
                    Character.project_id == project_id,
                    Character.id.in_(ctx.character_ids),
                )
            )
            .scalars()
            .all()
        )
    characters_text = format_characters(chars)

    return world_setting, style_guide, constraints, outline_text, characters_text


def _format_chapter_generate_instruction(*, mode: Literal["replace", "append"], base_instruction: str) -> str:
    instruction = base_instruction
    if mode == "append":
        instruction = "【追加模式】只输出需要追加到正文末尾的新增片段，不要重复已写内容。\\n" + instruction
    else:
        instruction = "【替换模式】输出完整替换稿（整章）。\\n" + instruction
    return instruction


def build_chapter_generate_render_values(
    db: Session,
    *,
    project: Project,
    chapter: Chapter,
    body: ChapterGenerateRequest,
) -> tuple[dict[str, object], str, dict[str, object]]:
    world_setting, style_guide, constraints, outline_text, characters_text = _load_project_story_text_context(
        db,
        project_id=chapter.project_id,
        outline_id=chapter.outline_id,
        ctx=body.context,
    )

    prev_text, prev_ending = load_previous_chapter_context(
        db,
        project_id=chapter.project_id,
        outline_id=chapter.outline_id,
        chapter_number=int(chapter.number),
        previous_chapter=body.context.previous_chapter,
    )

    current_draft_tail = ""
    if body.mode == "append":
        current_draft_tail = resolve_current_draft_tail(chapter=chapter, request_tail=body.context.current_draft_tail)

    smart_recent_summaries = ""
    smart_recent_full = ""
    smart_story_skeleton = ""
    if body.context.include_smart_context:
        smart_recent_summaries, smart_recent_full, smart_story_skeleton = build_smart_context(
            db,
            project_id=chapter.project_id,
            outline_id=chapter.outline_id,
            chapter_number=int(chapter.number),
        )

    base_instruction = body.instruction.strip()
    instruction = _format_chapter_generate_instruction(mode=body.mode, base_instruction=base_instruction)

    requirements_obj: dict[str, object] = {}
    if body.target_word_count is not None:
        requirements_obj["target_word_count"] = body.target_word_count
    requirements_text = json.dumps(requirements_obj, ensure_ascii=False, indent=2) if requirements_obj else ""

    values: dict[str, object] = {
        "mode": body.mode,
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
        "previous_chapter_ending": prev_ending,
        "current_draft_tail": current_draft_tail,
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
        "chapter_title": (chapter.title or ""),
        "chapter_plan": (chapter.plan or ""),
        "previous_chapter": prev_text,
        "previous_chapter_ending": prev_ending,
        "mode": body.mode,
        "current_draft_tail": current_draft_tail,
        "smart_context_recent_summaries": smart_recent_summaries,
        "smart_context_recent_full": smart_recent_full,
        "smart_context_story_skeleton": smart_story_skeleton,
    }
    values["user"] = {"instruction": instruction, "requirements": requirements_obj}

    return values, base_instruction, requirements_obj
