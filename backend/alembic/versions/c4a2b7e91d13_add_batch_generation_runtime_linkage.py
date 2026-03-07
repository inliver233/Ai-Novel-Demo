"""add batch generation runtime linkage

Revision ID: c4a2b7e91d13
Revises: b7c4f2e6a901
Create Date: 2026-03-07 17:48:23.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c4a2b7e91d13"
down_revision = "b7c4f2e6a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("batch_generation_tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("project_task_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("pause_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("checkpoint_json", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_batch_generation_tasks_project_task_id_project_tasks",
            "project_tasks",
            ["project_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_batch_generation_tasks_project_task_id", ["project_task_id"], unique=True)

    with op.batch_alter_table("batch_generation_task_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("last_request_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("last_error_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("batch_generation_task_items", schema=None) as batch_op:
        batch_op.drop_column("finished_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("last_error_json")
        batch_op.drop_column("last_request_id")
        batch_op.drop_column("attempt_count")

    with op.batch_alter_table("batch_generation_tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_batch_generation_tasks_project_task_id")
        batch_op.drop_constraint("fk_batch_generation_tasks_project_task_id_project_tasks", type_="foreignkey")
        batch_op.drop_column("checkpoint_json")
        batch_op.drop_column("pause_requested")
        batch_op.drop_column("skipped_count")
        batch_op.drop_column("failed_count")
        batch_op.drop_column("project_task_id")
