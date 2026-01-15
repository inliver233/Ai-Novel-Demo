"""add vector rerank config to project settings

Revision ID: 055a86b053de
Revises: af542aa52b66
Create Date: 2026-01-15 17:19:59.645876

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '055a86b053de'
down_revision = 'af542aa52b66'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_settings", sa.Column("vector_rerank_enabled", sa.Boolean(), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_method", sa.String(length=64), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_top_k", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_settings", "vector_rerank_top_k")
    op.drop_column("project_settings", "vector_rerank_method")
    op.drop_column("project_settings", "vector_rerank_enabled")
