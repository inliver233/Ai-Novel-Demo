"""add llm_profiles api_key_ciphertext/api_key_masked

Revision ID: 3d1c1e8a9f0b
Revises: 2f6b9f4a0c1e
Create Date: 2025-12-21 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "3d1c1e8a9f0b"
down_revision = "2f6b9f4a0c1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_key_ciphertext", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("api_key_masked", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.drop_column("api_key_masked")
        batch_op.drop_column("api_key_ciphertext")

