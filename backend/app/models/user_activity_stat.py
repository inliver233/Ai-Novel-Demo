from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class UserActivityStat(Base):
    __tablename__ = "user_activity_stats"

    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_seen_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


Index("ix_user_activity_stats_last_seen_at", UserActivityStat.last_seen_at)
