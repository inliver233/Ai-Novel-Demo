"""add admin user stats tables

Revision ID: 64ef818ef343
Revises: a4f9e5c7d2b1
Create Date: 2026-03-05

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "64ef818ef343"
down_revision = "a4f9e5c7d2b1"
branch_labels = None
depends_on = None


def _backfill_user_usage_stats() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    char_len_fn = "char_length" if dialect == "postgresql" else "length"

    op.execute(
        f"""
        INSERT INTO user_usage_stats (
            user_id,
            total_generation_calls,
            total_generation_error_calls,
            total_generated_chars,
            last_generation_at,
            created_at,
            updated_at
        )
        SELECT
            gr.actor_user_id AS user_id,
            COUNT(1) AS total_generation_calls,
            SUM(CASE WHEN gr.error_json IS NOT NULL AND TRIM(gr.error_json) <> '' THEN 1 ELSE 0 END) AS total_generation_error_calls,
            SUM({char_len_fn}(COALESCE(gr.output_text, ''))) AS total_generated_chars,
            MAX(gr.created_at) AS last_generation_at,
            CURRENT_TIMESTAMP AS created_at,
            CURRENT_TIMESTAMP AS updated_at
        FROM generation_runs gr
        JOIN users u ON u.id = gr.actor_user_id
        WHERE gr.actor_user_id IS NOT NULL AND TRIM(gr.actor_user_id) <> ''
        GROUP BY gr.actor_user_id
        """
    )


def upgrade() -> None:
    op.create_table(
        "user_activity_stats",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_request_id", sa.String(length=64), nullable=True),
        sa.Column("last_seen_path", sa.String(length=255), nullable=True),
        sa.Column("last_seen_method", sa.String(length=16), nullable=True),
        sa.Column("last_seen_status", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_user_activity_stats_last_seen_at", "user_activity_stats", ["last_seen_at"], unique=False)

    op.create_table(
        "user_usage_stats",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("total_generation_calls", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_generation_error_calls", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_generated_chars", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_generation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_user_usage_stats_last_generation_at", "user_usage_stats", ["last_generation_at"], unique=False)

    op.create_index(
        "ix_generation_runs_actor_user_id_created_at",
        "generation_runs",
        ["actor_user_id", "created_at"],
        unique=False,
    )
    _backfill_user_usage_stats()


def downgrade() -> None:
    op.drop_index("ix_generation_runs_actor_user_id_created_at", table_name="generation_runs")
    op.drop_index("ix_user_usage_stats_last_generation_at", table_name="user_usage_stats")
    op.drop_table("user_usage_stats")
    op.drop_index("ix_user_activity_stats_last_seen_at", table_name="user_activity_stats")
    op.drop_table("user_activity_stats")
