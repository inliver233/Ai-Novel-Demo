from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class PlotAnalysis(Base):
    __tablename__ = "plot_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)

    analysis_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    overall_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coherence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pacing_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_report_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (UniqueConstraint("chapter_id", name="uq_plot_analysis_chapter_id"),)


Index("ix_plot_analysis_project_id_created_at", PlotAnalysis.project_id, PlotAnalysis.created_at)
Index("ix_plot_analysis_project_id_chapter_id", PlotAnalysis.project_id, PlotAnalysis.chapter_id)

