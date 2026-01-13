"""add memory_tasks table

Revision ID: 478d3bb289da
Revises: 69b84930b3f8
Create Date: 2026-01-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "478d3bb289da"
down_revision = "69b84930b3f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("change_set_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name="ck_memory_tasks_status",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["change_set_id"], ["memory_change_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("change_set_id", "kind", name="uq_memory_tasks_change_set_kind"),
    )
    op.create_index("ix_memory_tasks_project_id", "memory_tasks", ["project_id"])
    op.create_index("ix_memory_tasks_change_set_id", "memory_tasks", ["change_set_id"])
    op.create_index("ix_memory_tasks_status", "memory_tasks", ["status"])
    op.create_index("ix_memory_tasks_kind", "memory_tasks", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_memory_tasks_kind", table_name="memory_tasks")
    op.drop_index("ix_memory_tasks_status", table_name="memory_tasks")
    op.drop_index("ix_memory_tasks_change_set_id", table_name="memory_tasks")
    op.drop_index("ix_memory_tasks_project_id", table_name="memory_tasks")
    op.drop_table("memory_tasks")

