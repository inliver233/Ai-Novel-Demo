"""add prompt_preset category

Revision ID: a8467b6f0518
Revises: 055a86b053de
Create Date: 2026-01-18 00:50:17.316598

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a8467b6f0518'
down_revision = '055a86b053de'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_presets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_presets", schema=None) as batch_op:
        batch_op.drop_column("category")
