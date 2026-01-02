from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chapter import Chapter

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

