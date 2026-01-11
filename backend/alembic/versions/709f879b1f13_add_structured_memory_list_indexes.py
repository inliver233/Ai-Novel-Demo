"""add structured memory list indexes

Revision ID: 709f879b1f13
Revises: 039b3f10165b
Create Date: 2026-01-12 07:44:45.832564

"""

from __future__ import annotations

from alembic import op


revision = "709f879b1f13"
down_revision = "039b3f10165b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_entities_project_id_deleted_at_updated_at",
        "entities",
        ["project_id", "deleted_at", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_relations_project_id_deleted_at_updated_at",
        "relations",
        ["project_id", "deleted_at", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_events_project_id_deleted_at_updated_at",
        "events",
        ["project_id", "deleted_at", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_foreshadows_project_id_deleted_at_updated_at",
        "foreshadows",
        ["project_id", "deleted_at", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_project_id_deleted_at_created_at",
        "evidence",
        ["project_id", "deleted_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_project_id_deleted_at_created_at", table_name="evidence")
    op.drop_index("ix_foreshadows_project_id_deleted_at_updated_at", table_name="foreshadows")
    op.drop_index("ix_events_project_id_deleted_at_updated_at", table_name="events")
    op.drop_index("ix_relations_project_id_deleted_at_updated_at", table_name="relations")
    op.drop_index("ix_entities_project_id_deleted_at_updated_at", table_name="entities")
