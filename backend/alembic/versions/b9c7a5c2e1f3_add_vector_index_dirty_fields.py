"""add vector index dirty fields

Revision ID: b9c7a5c2e1f3
Revises: a8467b6f0518
Create Date: 2026-01-18 20:22:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b9c7a5c2e1f3"
down_revision = "a8467b6f0518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    with op.batch_alter_table("project_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vector_index_dirty", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("last_vector_build_at", sa.DateTime(timezone=True), nullable=True))

    if dialect != "sqlite":
        op.alter_column("project_settings", "vector_index_dirty", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("project_settings", schema=None) as batch_op:
        batch_op.drop_column("last_vector_build_at")
        batch_op.drop_column("vector_index_dirty")

