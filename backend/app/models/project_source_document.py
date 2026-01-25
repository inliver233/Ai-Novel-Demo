from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class ProjectSourceDocument(Base):
    __tablename__ = "project_source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, default="txt")
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    kb_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vector_ingest_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    worldbook_proposal_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_memory_proposal_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ProjectSourceDocumentChunk(Base):
    __tablename__ = "project_source_document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("project_source_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    vector_chunk_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_project_source_document_chunks_document_index"),
    )


Index("ix_project_source_documents_project_id", ProjectSourceDocument.project_id)
Index("ix_project_source_documents_status", ProjectSourceDocument.status)
Index("ix_project_source_document_chunks_document_id", ProjectSourceDocumentChunk.document_id)

