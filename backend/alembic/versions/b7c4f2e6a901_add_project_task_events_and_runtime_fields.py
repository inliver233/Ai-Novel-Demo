"""add project task events and runtime fields

Revision ID: b7c4f2e6a901
Revises: 64ef818ef343
Create Date: 2026-03-07 02:08:34.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b7c4f2e6a901"
down_revision = "64ef818ef343"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_index("ix_project_tasks_status_heartbeat_at", ["status", "heartbeat_at"], unique=False)

    op.create_table(
        "project_task_events",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["project_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_project_task_events_project_seq", "project_task_events", ["project_id", "seq"], unique=False)
    op.create_index("ix_project_task_events_task_seq", "project_task_events", ["task_id", "seq"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_task_events_task_seq", table_name="project_task_events")
    op.drop_index("ix_project_task_events_project_seq", table_name="project_task_events")
    op.drop_table("project_task_events")

    with op.batch_alter_table("project_tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_project_tasks_status_heartbeat_at")
        batch_op.drop_column("attempt")
        batch_op.drop_column("heartbeat_at")
