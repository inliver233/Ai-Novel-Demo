"""merge heads

Revision ID: dfb3c3ed0847
Revises: 2c72bcfbae89, 8b4c2f3a1d9e
Create Date: 2026-01-02 19:05:12.731908

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'dfb3c3ed0847'
down_revision = ('2c72bcfbae89', '8b4c2f3a1d9e')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

