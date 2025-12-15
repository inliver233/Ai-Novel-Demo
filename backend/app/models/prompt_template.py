from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now_iso


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    system_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now_iso, onupdate=utc_now_iso)

    __table_args__ = (UniqueConstraint("project_id", "type", name="uq_prompt_templates_project_id_type"),)


Index("ix_prompt_templates_project_id", PromptTemplate.project_id)

