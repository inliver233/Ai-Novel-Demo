"""add query preprocessing config to project settings

Revision ID: af542aa52b66
Revises: 478d3bb289da
Create Date: 2026-01-15 03:39:09.322636

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'af542aa52b66'
down_revision = '478d3bb289da'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_settings", sa.Column("query_preprocessing_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_settings", "query_preprocessing_json")
