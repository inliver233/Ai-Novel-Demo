"""add prompt presets and blocks

Revision ID: d8993729ae5a
Revises: 3d1c1e8a9f0b
Create Date: 2025-12-22 15:25:10.663257

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'd8993729ae5a'
down_revision = '3d1c1e8a9f0b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_presets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active_for_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("prompt_presets", schema=None) as batch_op:
        batch_op.create_index("ix_prompt_presets_project_id", ["project_id"], unique=False)

    op.create_table(
        "prompt_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("preset_id", sa.String(length=36), nullable=False),
        sa.Column("identifier", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("template", sa.Text(), nullable=True),
        sa.Column("marker_key", sa.String(length=255), nullable=True),
        sa.Column("injection_position", sa.String(length=16), nullable=False),
        sa.Column("injection_depth", sa.Integer(), nullable=True),
        sa.Column("injection_order", sa.Integer(), nullable=False),
        sa.Column("triggers_json", sa.Text(), nullable=True),
        sa.Column("forbid_overrides", sa.Boolean(), nullable=False),
        sa.Column("budget_json", sa.Text(), nullable=True),
        sa.Column("cache_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["preset_id"], ["prompt_presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("prompt_blocks", schema=None) as batch_op:
        batch_op.create_index("ix_prompt_blocks_preset_id", ["preset_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("prompt_blocks", schema=None) as batch_op:
        batch_op.drop_index("ix_prompt_blocks_preset_id")

    op.drop_table("prompt_blocks")

    with op.batch_alter_table("prompt_presets", schema=None) as batch_op:
        batch_op.drop_index("ix_prompt_presets_project_id")

    op.drop_table("prompt_presets")
