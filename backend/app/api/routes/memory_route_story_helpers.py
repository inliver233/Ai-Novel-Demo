from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.chapter import Chapter
from app.models.project_settings import ProjectSettings
from app.models.story_memory import StoryMemory

StoryMemoryOpenLoopOrder = Literal['timeline_desc', 'importance_desc', 'updated_desc']
ALLOWED_STORY_MEMORY_OPEN_LOOP_ORDERS: tuple[StoryMemoryOpenLoopOrder, ...] = (
    'timeline_desc',
    'importance_desc',
    'updated_desc',
)


@dataclass(frozen=True)
class StoryMemoryOpenLoopsArgs:
    q_norm: str
    order_norm: StoryMemoryOpenLoopOrder


def _validate_story_memory_import_schema_version(schema_version: str | None) -> None:
    if str(schema_version or '').strip() != 'story_memory_import_v1':
        raise AppError.validation(details={'reason': 'unsupported_schema_version', 'schema_version': schema_version})


def _ensure_story_memory_rebuild_dirty(db: Session, *, project_id: str, flush_on_create: bool = False) -> None:
    settings_row = db.get(ProjectSettings, project_id)
    if settings_row is None:
        settings_row = ProjectSettings(project_id=project_id)
        db.add(settings_row)
        if flush_on_create:
            db.flush()
    settings_row.vector_index_dirty = True


def _normalize_story_memory_open_loops_args(*, q: str | None, order: str | None) -> StoryMemoryOpenLoopsArgs:
    q_norm = str(q or '').strip()
    order_norm = str(order or '').strip().lower() or 'timeline_desc'
    if order_norm not in ALLOWED_STORY_MEMORY_OPEN_LOOP_ORDERS:
        raise AppError.validation(
            message='不支持的排序字段',
            details={'order': order_norm, 'allowed': sorted(ALLOWED_STORY_MEMORY_OPEN_LOOP_ORDERS)},
        )
    return StoryMemoryOpenLoopsArgs(q_norm=q_norm, order_norm=order_norm)


def _list_story_memory_open_loop_rows(
    db: Session,
    *,
    project_id: str,
    limit: int,
    args: StoryMemoryOpenLoopsArgs,
) -> tuple[list[StoryMemory], bool]:
    filters = [
        StoryMemory.project_id == project_id,
        StoryMemory.is_foreshadow == 1,  # noqa: E712
        StoryMemory.foreshadow_resolved_at_chapter_id.is_(None),
    ]
    if args.q_norm:
        pattern = f'%{args.q_norm}%'
        filters.append(or_(StoryMemory.title.ilike(pattern), StoryMemory.content.ilike(pattern)))

    if args.order_norm == 'importance_desc':
        order_by = (StoryMemory.importance_score.desc(), StoryMemory.story_timeline.desc(), StoryMemory.updated_at.desc())
    elif args.order_norm == 'updated_desc':
        order_by = (StoryMemory.updated_at.desc(), StoryMemory.story_timeline.desc(), StoryMemory.importance_score.desc())
    else:
        order_by = (StoryMemory.story_timeline.desc(), StoryMemory.importance_score.desc(), StoryMemory.updated_at.desc())

    rows = (
        db.execute(select(StoryMemory).where(*filters).order_by(*order_by).limit(int(limit) + 1)).scalars().all()
    )
    has_more = len(rows) > int(limit)
    return rows[: int(limit)], has_more


def _require_story_memory_foreshadow(db: Session, *, project_id: str, story_memory_id: str) -> StoryMemory:
    row = db.get(StoryMemory, story_memory_id)
    if row is None or str(row.project_id) != str(project_id):
        raise AppError.not_found()
    if not bool(getattr(row, 'is_foreshadow', 0)):
        raise AppError.validation(message='该 StoryMemory 不是伏笔（foreshadow）', details={'story_memory_id': story_memory_id})
    return row


def _normalize_story_memory_resolved_at_chapter_id(
    db: Session,
    *,
    project_id: str,
    resolved_at_chapter_id: str | None,
) -> str | None:
    chapter_id = str(resolved_at_chapter_id or '').strip() or None
    if not chapter_id:
        return None
    chapter = db.get(Chapter, chapter_id)
    if chapter is None or str(getattr(chapter, 'project_id', '')) != str(project_id):
        raise AppError.validation(
            message='回收章节（resolved_at_chapter_id）无效或不属于当前项目',
            details={'resolved_at_chapter_id': chapter_id},
        )
    return chapter_id
