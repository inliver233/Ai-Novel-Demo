from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMPreset(Base):
    __tablename__ = "llm_presets"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    presence_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    frequency_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
