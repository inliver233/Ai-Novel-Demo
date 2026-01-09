from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class StoryMemory(Base):
    __tablename__ = "story_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    full_context_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_timeline: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    text_position: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_foreshadow: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    foreshadow_resolved_at_chapter_id: Mapped[str | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


Index("ix_story_memories_project_id_chapter_id", StoryMemory.project_id, StoryMemory.chapter_id)
Index("ix_story_memories_project_id_story_timeline", StoryMemory.project_id, StoryMemory.story_timeline)
Index(
    "ix_story_memories_project_id_memory_type_importance",
    StoryMemory.project_id,
    StoryMemory.memory_type,
    StoryMemory.importance_score,
)
