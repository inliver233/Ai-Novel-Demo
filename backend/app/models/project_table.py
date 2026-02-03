from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class ProjectTable(Base):
    __tablename__ = "project_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    table_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    auto_update_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("project_id", "table_key", name="uq_project_tables_project_id_table_key"),)


class ProjectTableRow(Base):
    __tablename__ = "project_table_rows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    table_id: Mapped[str] = mapped_column(ForeignKey("project_tables.id", ondelete="CASCADE"), nullable=False)

    row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


Index("ix_project_tables_project_id", ProjectTable.project_id)
Index("ix_project_tables_project_id_table_key", ProjectTable.project_id, ProjectTable.table_key)
Index("ix_project_table_rows_project_id", ProjectTableRow.project_id)
Index("ix_project_table_rows_table_id", ProjectTableRow.table_id)
Index("ix_project_table_rows_table_id_row_index", ProjectTableRow.table_id, ProjectTableRow.row_index)
