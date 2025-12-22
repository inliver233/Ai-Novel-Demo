"""add generation_runs prompt_render_log_json

Revision ID: f078e253d338
Revises: d8993729ae5a
Create Date: 2025-12-22 16:11:51.496288

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'f078e253d338'
down_revision = 'd8993729ae5a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generation_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prompt_render_log_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_runs", schema=None) as batch_op:
        batch_op.drop_column("prompt_render_log_json")
