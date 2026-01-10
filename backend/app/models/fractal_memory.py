from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class FractalMemory(Base):
    __tablename__ = "fractal_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    arcs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sagas_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("project_id", name="uq_fractal_memory_project_id"),)


Index("ix_fractal_memory_project_id", FractalMemory.project_id)

