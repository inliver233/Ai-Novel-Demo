from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base
from app.db.utils import utc_now


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer','editor','owner')",
            name="ck_project_memberships_role",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    @validates("role")
    def _validate_role(self, _key: str, value: str) -> str:
        role = (value or "").strip().lower()
        if role not in ("viewer", "editor", "owner"):
            raise ValueError("invalid project membership role")
        return role


Index("ix_project_memberships_project_id", ProjectMembership.project_id)
Index("ix_project_memberships_user_id", ProjectMembership.user_id)
