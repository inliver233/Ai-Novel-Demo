"""add embedding provider config to project_settings

Revision ID: 09930c9ce083
Revises: b9c7a5c2e1f3
Create Date: 2026-01-19 19:18:04.165679

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '09930c9ce083'
down_revision = 'b9c7a5c2e1f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_settings", sa.Column("vector_embedding_provider", sa.String(length=64), nullable=True))
    op.add_column("project_settings", sa.Column("vector_embedding_azure_deployment", sa.String(length=255), nullable=True))
    op.add_column("project_settings", sa.Column("vector_embedding_azure_api_version", sa.String(length=64), nullable=True))
    op.add_column("project_settings", sa.Column("vector_embedding_sentence_transformers_model", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("project_settings", "vector_embedding_sentence_transformers_model")
    op.drop_column("project_settings", "vector_embedding_azure_api_version")
    op.drop_column("project_settings", "vector_embedding_azure_deployment")
    op.drop_column("project_settings", "vector_embedding_provider")
