from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class WorldBookEntry(Base):
    __tablename__ = "worldbook_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    constant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    keywords_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    exclude_recursion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prevent_recursion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=12000)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="important")

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


Index("ix_worldbook_entries_project_id_enabled", WorldBookEntry.project_id, WorldBookEntry.enabled)
Index("ix_worldbook_entries_project_id_constant_enabled", WorldBookEntry.project_id, WorldBookEntry.constant, WorldBookEntry.enabled)
