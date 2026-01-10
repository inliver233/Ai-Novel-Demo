"""add postgres extensions

Revision ID: 9b6366ef8065
Revises: 31c0665707d6
Create Date: 2026-01-10 20:55:43.081413

"""

from __future__ import annotations

from alembic import op


revision = '9b6366ef8065'
down_revision = '31c0665707d6'
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    # Required for future PG features (pgvector) and text search optimizations.
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
