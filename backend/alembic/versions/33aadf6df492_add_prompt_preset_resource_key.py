"""add prompt_preset resource_key

Revision ID: 33aadf6df492
Revises: 166a3fc3e56a
Create Date: 2026-01-24 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "33aadf6df492"
down_revision = "166a3fc3e56a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_presets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resource_key", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_presets", schema=None) as batch_op:
        batch_op.drop_column("resource_key")

