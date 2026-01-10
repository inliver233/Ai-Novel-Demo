"""add structured memory tables

Revision ID: f89622011fdb
Revises: 9b6366ef8065
Create Date: 2026-01-11 00:39:57.431118

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'f89622011fdb'
down_revision = '9b6366ef8065'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("summary_md", sa.Text(), nullable=True),
        sa.Column("attributes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "entity_type", "name", name="uq_entities_project_type_name"),
    )
    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.create_index("ix_entities_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_entities_project_id_entity_type", ["project_id", "entity_type"], unique=False)

    op.create_table(
        "relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("from_entity_id", sa.String(length=36), nullable=False),
        sa.Column("to_entity_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=True),
        sa.Column("attributes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "from_entity_id",
            "to_entity_id",
            "relation_type",
            name="uq_relations_project_from_to_type",
        ),
    )
    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.create_index("ix_relations_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_relations_project_id_from_entity_id", ["project_id", "from_entity_id"], unique=False)
        batch_op.create_index("ix_relations_project_id_to_entity_id", ["project_id", "to_entity_id"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("attributes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.create_index("ix_events_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_events_project_id_chapter_id", ["project_id", "chapter_id"], unique=False)

    op.create_table(
        "foreshadows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_at_chapter_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Integer(), nullable=False),
        sa.Column("attributes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_at_chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("foreshadows", schema=None) as batch_op:
        batch_op.create_index("ix_foreshadows_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_foreshadows_project_id_resolved", ["project_id", "resolved"], unique=False)

    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("quote_md", sa.Text(), nullable=False),
        sa.Column("attributes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.create_index("ix_evidence_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_evidence_project_id_source", ["project_id", "source_type", "source_id"], unique=False)

    op.create_table(
        "memory_change_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("generation_run_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("summary_md", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed','applied','rolled_back','failed')",
            name="ck_memory_change_sets_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_memory_change_sets_project_idempotency_key"),
    )
    with op.batch_alter_table("memory_change_sets", schema=None) as batch_op:
        batch_op.create_index("ix_memory_change_sets_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_memory_change_sets_project_id_status", ["project_id", "status"], unique=False)

    op.create_table(
        "memory_change_set_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("change_set_id", sa.String(length=36), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("target_table", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("op", sa.String(length=16), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("evidence_ids_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("op IN ('upsert','delete')", name="ck_memory_change_set_items_op"),
        sa.CheckConstraint(
            "target_table IN ('entities','relations','events','foreshadows','evidence')",
            name="ck_memory_change_set_items_target_table",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["change_set_id"], ["memory_change_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("change_set_id", "item_index", name="uq_memory_change_set_items_change_set_index"),
    )
    with op.batch_alter_table("memory_change_set_items", schema=None) as batch_op:
        batch_op.create_index("ix_memory_change_set_items_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_memory_change_set_items_change_set_id", ["change_set_id"], unique=False)
        batch_op.create_index("ix_memory_change_set_items_project_target", ["project_id", "target_table"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("memory_change_set_items", schema=None) as batch_op:
        batch_op.drop_index("ix_memory_change_set_items_project_target")
        batch_op.drop_index("ix_memory_change_set_items_change_set_id")
        batch_op.drop_index("ix_memory_change_set_items_project_id")

    op.drop_table("memory_change_set_items")

    with op.batch_alter_table("memory_change_sets", schema=None) as batch_op:
        batch_op.drop_index("ix_memory_change_sets_project_id_status")
        batch_op.drop_index("ix_memory_change_sets_project_id")

    op.drop_table("memory_change_sets")

    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.drop_index("ix_evidence_project_id_source")
        batch_op.drop_index("ix_evidence_project_id")

    op.drop_table("evidence")

    with op.batch_alter_table("foreshadows", schema=None) as batch_op:
        batch_op.drop_index("ix_foreshadows_project_id_resolved")
        batch_op.drop_index("ix_foreshadows_project_id")

    op.drop_table("foreshadows")

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_index("ix_events_project_id_chapter_id")
        batch_op.drop_index("ix_events_project_id")

    op.drop_table("events")

    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.drop_index("ix_relations_project_id_to_entity_id")
        batch_op.drop_index("ix_relations_project_id_from_entity_id")
        batch_op.drop_index("ix_relations_project_id")

    op.drop_table("relations")

    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.drop_index("ix_entities_project_id_entity_type")
        batch_op.drop_index("ix_entities_project_id")

    op.drop_table("entities")
