"""add knowledge_bases.priority_group

Revision ID: 714c1b58c136
Revises: ed12de854702
Create Date: 2026-01-24 06:53:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "714c1b58c136"
down_revision = "ed12de854702"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("priority_group", sa.String(length=16), nullable=False, server_default="normal"))

    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.alter_column("priority_group", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.drop_column("priority_group")

