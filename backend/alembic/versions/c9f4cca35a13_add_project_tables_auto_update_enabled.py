"""add project_tables auto_update_enabled

Revision ID: c9f4cca35a13
Revises: e1c65f9a82c6
Create Date: 2026-02-04 03:05:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c9f4cca35a13"
down_revision = "e1c65f9a82c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    with op.batch_alter_table("project_tables", schema=None) as batch_op:
        batch_op.add_column(sa.Column("auto_update_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

    if dialect != "sqlite":
        op.alter_column("project_tables", "auto_update_enabled", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("project_tables", schema=None) as batch_op:
        batch_op.drop_column("auto_update_enabled")

