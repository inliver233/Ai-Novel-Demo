"""drop llm_profiles.api_key

Revision ID: 2f6b9f4a0c1e
Revises: 1c2a0e6b4c2d
Create Date: 2025-12-18 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "2f6b9f4a0c1e"
down_revision = "1c2a0e6b4c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.drop_column("api_key")


def downgrade() -> None:
    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_key", sa.Text(), nullable=False, server_default=""))

    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.alter_column("api_key", server_default=None)

