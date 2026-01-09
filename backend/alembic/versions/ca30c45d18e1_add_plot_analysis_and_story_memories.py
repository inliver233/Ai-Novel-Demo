"""add plot_analysis and story_memories

Revision ID: ca30c45d18e1
Revises: 76954388cbe7
Create Date: 2026-01-10 01:40:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "ca30c45d18e1"
down_revision = "76954388cbe7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plot_analysis",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_json", sa.Text(), nullable=False),
        sa.Column("overall_quality_score", sa.Float(), nullable=True),
        sa.Column("coherence_score", sa.Float(), nullable=True),
        sa.Column("engagement_score", sa.Float(), nullable=True),
        sa.Column("pacing_score", sa.Float(), nullable=True),
        sa.Column("analysis_report_md", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", name="uq_plot_analysis_chapter_id"),
    )
    with op.batch_alter_table("plot_analysis", schema=None) as batch_op:
        batch_op.create_index("ix_plot_analysis_project_id_chapter_id", ["project_id", "chapter_id"], unique=False)
        batch_op.create_index("ix_plot_analysis_project_id_created_at", ["project_id", "created_at"], unique=False)

    op.create_table(
        "story_memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=36), nullable=True),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("full_context_md", sa.Text(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("story_timeline", sa.Integer(), nullable=False),
        sa.Column("text_position", sa.Integer(), nullable=False),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("is_foreshadow", sa.Integer(), nullable=False),
        sa.Column("foreshadow_resolved_at_chapter_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["foreshadow_resolved_at_chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("story_memories", schema=None) as batch_op:
        batch_op.create_index("ix_story_memories_project_id_chapter_id", ["project_id", "chapter_id"], unique=False)
        batch_op.create_index(
            "ix_story_memories_project_id_memory_type_importance",
            ["project_id", "memory_type", "importance_score"],
            unique=False,
        )
        batch_op.create_index("ix_story_memories_project_id_story_timeline", ["project_id", "story_timeline"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("story_memories", schema=None) as batch_op:
        batch_op.drop_index("ix_story_memories_project_id_story_timeline")
        batch_op.drop_index("ix_story_memories_project_id_memory_type_importance")
        batch_op.drop_index("ix_story_memories_project_id_chapter_id")

    op.drop_table("story_memories")

    with op.batch_alter_table("plot_analysis", schema=None) as batch_op:
        batch_op.drop_index("ix_plot_analysis_project_id_created_at")
        batch_op.drop_index("ix_plot_analysis_project_id_chapter_id")

    op.drop_table("plot_analysis")

