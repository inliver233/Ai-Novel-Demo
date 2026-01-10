"""add fractal_memory table

Revision ID: 2662fe2e5a01
Revises: 4858b08a6519
Create Date: 2026-01-10

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2662fe2e5a01"
down_revision = "4858b08a6519"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fractal_memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("scenes_json", sa.Text(), nullable=False),
        sa.Column("arcs_json", sa.Text(), nullable=False),
        sa.Column("sagas_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_fractal_memory_project_id"),
    )
    with op.batch_alter_table("fractal_memory", schema=None) as batch_op:
        batch_op.create_index("ix_fractal_memory_project_id", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_table("fractal_memory")

