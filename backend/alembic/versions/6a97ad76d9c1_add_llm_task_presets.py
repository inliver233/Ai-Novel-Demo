"""add llm_task_presets

Revision ID: 6a97ad76d9c1
Revises: 171d29cc0501
Create Date: 2026-03-04

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "6a97ad76d9c1"
down_revision = "171d29cc0501"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_task_presets",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("llm_profile_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("presence_penalty", sa.Float(), nullable=True),
        sa.Column("frequency_penalty", sa.Float(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("stop_json", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_profile_id"], ["llm_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "task_key"),
    )
    op.create_index("ix_llm_task_presets_project_id", "llm_task_presets", ["project_id"])
    op.create_index("ix_llm_task_presets_llm_profile_id", "llm_task_presets", ["llm_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_task_presets_llm_profile_id", table_name="llm_task_presets")
    op.drop_index("ix_llm_task_presets_project_id", table_name="llm_task_presets")
    op.drop_table("llm_task_presets")
