"""add_vector_rerank_project_config

Revision ID: 902bd83f86ed
Revises: 4c971683d6cb
Create Date: 2026-01-30 17:42:40.903122

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '902bd83f86ed'
down_revision = '4c971683d6cb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_settings", sa.Column("vector_rerank_provider", sa.String(length=64), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_base_url", sa.String(length=2048), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_model", sa.String(length=255), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_api_key_ciphertext", sa.Text(), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_api_key_masked", sa.String(length=64), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_timeout_seconds", sa.Integer(), nullable=True))
    op.add_column("project_settings", sa.Column("vector_rerank_hybrid_alpha", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_settings", "vector_rerank_hybrid_alpha")
    op.drop_column("project_settings", "vector_rerank_timeout_seconds")
    op.drop_column("project_settings", "vector_rerank_api_key_masked")
    op.drop_column("project_settings", "vector_rerank_api_key_ciphertext")
    op.drop_column("project_settings", "vector_rerank_model")
    op.drop_column("project_settings", "vector_rerank_base_url")
    op.drop_column("project_settings", "vector_rerank_provider")
