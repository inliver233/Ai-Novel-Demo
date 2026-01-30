from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class SearchDocument(Base):
    """
    External content table for SQLite FTS5 (`search_index` virtual table).

    Notes:
    - `id` is an INTEGER PRIMARY KEY (rowid) so FTS5 can reference it via `content_rowid='id'`.
    - The FTS5 table itself is created via Alembic using raw SQL because it is a virtual table.
    - Trigram tokenizer may be unavailable depending on the SQLite build; migration falls back to unicode61+prefix.
    """

    __tablename__ = "search_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    url_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    locator_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("project_id", "source_type", "source_id", name="uq_search_documents_project_id_source_type_source_id"),
    )


Index("ix_search_documents_project_id", SearchDocument.project_id)
Index("ix_search_documents_project_id_source_type", SearchDocument.project_id, SearchDocument.source_type)
