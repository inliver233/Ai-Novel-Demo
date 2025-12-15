from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now_iso


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logline: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now_iso, onupdate=utc_now_iso)


Index("ix_projects_owner_user_id", Project.owner_user_id)

