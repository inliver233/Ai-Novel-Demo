"""add batch generation tasks

Revision ID: 8b4c2f3a1d9e
Revises: f078e253d338
Create Date: 2026-01-02 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "8b4c2f3a1d9e"
down_revision = "f078e253d338"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batch_generation_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("outline_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outline_id"], ["outlines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_batch_generation_tasks_project_id", "batch_generation_tasks", ["project_id"])
    op.create_index("ix_batch_generation_tasks_status", "batch_generation_tasks", ["status"])

    op.create_table(
        "batch_generation_task_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("generation_run_id", sa.String(length=36), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["batch_generation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "chapter_number", name="uq_batch_generation_task_items_task_number"),
    )
    op.create_index("ix_batch_generation_task_items_task_id", "batch_generation_task_items", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_batch_generation_task_items_task_id", table_name="batch_generation_task_items")
    op.drop_table("batch_generation_task_items")

    op.drop_index("ix_batch_generation_tasks_status", table_name="batch_generation_tasks")
    op.drop_index("ix_batch_generation_tasks_project_id", table_name="batch_generation_tasks")
    op.drop_table("batch_generation_tasks")
