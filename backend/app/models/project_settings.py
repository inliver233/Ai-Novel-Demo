from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    world_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)

    vector_embedding_base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    vector_embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector_embedding_api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_embedding_api_key_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
