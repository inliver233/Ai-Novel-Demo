"""add vector embedding config to project_settings

Revision ID: 69b84930b3f8
Revises: 709f879b1f13
Create Date: 2026-01-13 17:49:20.075556

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '69b84930b3f8'
down_revision = '709f879b1f13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_settings", sa.Column("vector_embedding_base_url", sa.String(length=2048), nullable=True))
    op.add_column("project_settings", sa.Column("vector_embedding_model", sa.String(length=255), nullable=True))
    op.add_column("project_settings", sa.Column("vector_embedding_api_key_ciphertext", sa.Text(), nullable=True))
    op.add_column("project_settings", sa.Column("vector_embedding_api_key_masked", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("project_settings", "vector_embedding_api_key_masked")
    op.drop_column("project_settings", "vector_embedding_api_key_ciphertext")
    op.drop_column("project_settings", "vector_embedding_model")
    op.drop_column("project_settings", "vector_embedding_base_url")
