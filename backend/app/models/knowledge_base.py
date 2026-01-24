from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    kb_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default")

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority_group: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("project_id", "kb_id", name="uq_knowledge_bases_project_id_kb_id"),)


Index("ix_knowledge_bases_project_id", KnowledgeBase.project_id)
Index("ix_knowledge_bases_project_id_enabled", KnowledgeBase.project_id, KnowledgeBase.enabled)
Index("ix_knowledge_bases_project_id_order_index", KnowledgeBase.project_id, KnowledgeBase.order_index)
