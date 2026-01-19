from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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

    vector_embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vector_embedding_base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    vector_embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector_embedding_azure_deployment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector_embedding_azure_api_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vector_embedding_sentence_transformers_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector_embedding_api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_embedding_api_key_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)

    vector_rerank_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vector_rerank_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vector_rerank_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)

    query_preprocessing_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    vector_index_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_vector_build_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True)
