from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.utils import utc_now


class MemoryEntity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="generic")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "entity_type", "name", name="uq_entities_project_type_name"),)


class MemoryRelation(Base):
    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    to_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)

    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="related_to")
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "from_entity_id",
            "to_entity_id",
            "relation_type",
            name="uq_relations_project_from_to_type",
        ),
    )


class MemoryEvent(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="event")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attributes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryForeshadow(Base):
    __tablename__ = "foreshadows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    resolved_at_chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryEvidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quote_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attributes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryChangeSet(Base):
    __tablename__ = "memory_change_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generation_run_id: Mapped[str | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"), nullable=True)

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_memory_change_sets_project_idempotency_key"),
        CheckConstraint(
            "status IN ('proposed','applied','rolled_back','failed')",
            name="ck_memory_change_sets_status",
        ),
    )


class MemoryChangeSetItem(Base):
    __tablename__ = "memory_change_set_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    change_set_id: Mapped[str] = mapped_column(ForeignKey("memory_change_sets.id", ondelete="CASCADE"), nullable=False)

    item_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_table: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    op: Mapped[str] = mapped_column(String(16), nullable=False, default="upsert")

    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("change_set_id", "item_index", name="uq_memory_change_set_items_change_set_index"),
        CheckConstraint("op IN ('upsert','delete')", name="ck_memory_change_set_items_op"),
        CheckConstraint(
            "target_table IN ('entities','relations','events','foreshadows','evidence','project_table_rows')",
            name="ck_memory_change_set_items_target_table",
        ),
    )


Index("ix_entities_project_id", MemoryEntity.project_id)
Index("ix_entities_project_id_entity_type", MemoryEntity.project_id, MemoryEntity.entity_type)
Index(
    "ix_entities_project_id_deleted_at_updated_at",
    MemoryEntity.project_id,
    MemoryEntity.deleted_at,
    MemoryEntity.updated_at,
)
Index("ix_relations_project_id", MemoryRelation.project_id)
Index("ix_relations_project_id_from_entity_id", MemoryRelation.project_id, MemoryRelation.from_entity_id)
Index("ix_relations_project_id_to_entity_id", MemoryRelation.project_id, MemoryRelation.to_entity_id)
Index(
    "ix_relations_project_id_deleted_at_updated_at",
    MemoryRelation.project_id,
    MemoryRelation.deleted_at,
    MemoryRelation.updated_at,
)
Index("ix_events_project_id", MemoryEvent.project_id)
Index("ix_events_project_id_chapter_id", MemoryEvent.project_id, MemoryEvent.chapter_id)
Index(
    "ix_events_project_id_deleted_at_updated_at",
    MemoryEvent.project_id,
    MemoryEvent.deleted_at,
    MemoryEvent.updated_at,
)
Index("ix_foreshadows_project_id", MemoryForeshadow.project_id)
Index("ix_foreshadows_project_id_resolved", MemoryForeshadow.project_id, MemoryForeshadow.resolved)
Index(
    "ix_foreshadows_project_id_deleted_at_updated_at",
    MemoryForeshadow.project_id,
    MemoryForeshadow.deleted_at,
    MemoryForeshadow.updated_at,
)
Index("ix_evidence_project_id", MemoryEvidence.project_id)
Index("ix_evidence_project_id_source", MemoryEvidence.project_id, MemoryEvidence.source_type, MemoryEvidence.source_id)
Index(
    "ix_evidence_project_id_deleted_at_created_at",
    MemoryEvidence.project_id,
    MemoryEvidence.deleted_at,
    MemoryEvidence.created_at,
)
Index("ix_memory_change_sets_project_id", MemoryChangeSet.project_id)
Index("ix_memory_change_sets_project_id_status", MemoryChangeSet.project_id, MemoryChangeSet.status)
Index("ix_memory_change_set_items_project_id", MemoryChangeSetItem.project_id)
Index("ix_memory_change_set_items_change_set_id", MemoryChangeSetItem.change_set_id)
Index("ix_memory_change_set_items_project_target", MemoryChangeSetItem.project_id, MemoryChangeSetItem.target_table)
