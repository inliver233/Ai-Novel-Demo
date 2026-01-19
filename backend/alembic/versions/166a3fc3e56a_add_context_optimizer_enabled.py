"""add context optimizer enabled

Revision ID: 166a3fc3e56a
Revises: b368a03dc4b5
Create Date: 2026-01-19 23:25:24.076585

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '166a3fc3e56a'
down_revision = 'b368a03dc4b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    with op.batch_alter_table("project_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("context_optimizer_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    if dialect != "sqlite":
        op.alter_column("project_settings", "context_optimizer_enabled", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("project_settings", schema=None) as batch_op:
        batch_op.drop_column("context_optimizer_enabled")
