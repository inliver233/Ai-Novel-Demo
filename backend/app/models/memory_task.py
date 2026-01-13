from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class MemoryTask(Base):
    __tablename__ = "memory_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    change_set_id: Mapped[str] = mapped_column(ForeignKey("memory_change_sets.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")

    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("change_set_id", "kind", name="uq_memory_tasks_change_set_kind"),)


Index("ix_memory_tasks_project_id", MemoryTask.project_id)
Index("ix_memory_tasks_change_set_id", MemoryTask.change_set_id)
Index("ix_memory_tasks_status", MemoryTask.status)
Index("ix_memory_tasks_kind", MemoryTask.kind)

