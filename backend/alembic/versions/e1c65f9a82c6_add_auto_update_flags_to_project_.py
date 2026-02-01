"""add auto update flags to project_settings

Revision ID: e1c65f9a82c6
Revises: c036de4694b3
Create Date: 2026-02-01 21:57:33.948600

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'e1c65f9a82c6'
down_revision = 'c036de4694b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    cols = [
        "auto_update_worldbook_enabled",
        "auto_update_characters_enabled",
        "auto_update_story_memory_enabled",
        "auto_update_graph_enabled",
        "auto_update_vector_enabled",
        "auto_update_search_enabled",
        "auto_update_fractal_enabled",
        "auto_update_tables_enabled",
    ]

    with op.batch_alter_table("project_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("auto_update_worldbook_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_characters_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_story_memory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_graph_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_vector_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_search_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_fractal_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto_update_tables_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

    if dialect != "sqlite":
        for col in cols:
            op.alter_column("project_settings", col, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("project_settings", schema=None) as batch_op:
        batch_op.drop_column("auto_update_tables_enabled")
        batch_op.drop_column("auto_update_fractal_enabled")
        batch_op.drop_column("auto_update_search_enabled")
        batch_op.drop_column("auto_update_vector_enabled")
        batch_op.drop_column("auto_update_graph_enabled")
        batch_op.drop_column("auto_update_story_memory_enabled")
        batch_op.drop_column("auto_update_characters_enabled")
        batch_op.drop_column("auto_update_worldbook_enabled")
