"""add llm profile template fields

Revision ID: a4f9e5c7d2b1
Revises: 6a97ad76d9c1
Create Date: 2026-03-05

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a4f9e5c7d2b1"
down_revision = "6a97ad76d9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_profiles", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("llm_profiles", sa.Column("top_p", sa.Float(), nullable=True))
    op.add_column("llm_profiles", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_profiles", sa.Column("presence_penalty", sa.Float(), nullable=True))
    op.add_column("llm_profiles", sa.Column("frequency_penalty", sa.Float(), nullable=True))
    op.add_column("llm_profiles", sa.Column("top_k", sa.Integer(), nullable=True))
    op.add_column("llm_profiles", sa.Column("stop_json", sa.Text(), nullable=True))
    op.add_column("llm_profiles", sa.Column("timeout_seconds", sa.Integer(), nullable=True))
    op.add_column("llm_profiles", sa.Column("extra_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_profiles", "extra_json")
    op.drop_column("llm_profiles", "timeout_seconds")
    op.drop_column("llm_profiles", "stop_json")
    op.drop_column("llm_profiles", "top_k")
    op.drop_column("llm_profiles", "frequency_penalty")
    op.drop_column("llm_profiles", "presence_penalty")
    op.drop_column("llm_profiles", "max_tokens")
    op.drop_column("llm_profiles", "top_p")
    op.drop_column("llm_profiles", "temperature")
