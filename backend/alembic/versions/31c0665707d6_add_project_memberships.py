"""add project_memberships

Revision ID: 31c0665707d6
Revises: e17a2e45e8f0
Create Date: 2026-01-10 04:39:41.888459

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '31c0665707d6'
down_revision = 'e17a2e45e8f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_memberships",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner','editor','viewer')",
            name="ck_project_memberships_role",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    with op.batch_alter_table("project_memberships", schema=None) as batch_op:
        batch_op.create_index("ix_project_memberships_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_project_memberships_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("project_memberships", schema=None) as batch_op:
        batch_op.drop_index("ix_project_memberships_user_id")
        batch_op.drop_index("ix_project_memberships_project_id")

    op.drop_table("project_memberships")
