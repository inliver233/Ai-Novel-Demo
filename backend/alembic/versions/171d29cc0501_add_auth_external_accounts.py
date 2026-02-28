"""add auth_external_accounts

Revision ID: 171d29cc0501
Revises: c9f4cca35a13
Create Date: 2026-02-28

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "171d29cc0501"
down_revision = "c9f4cca35a13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_external_accounts",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("provider", "subject"),
    )
    op.create_index("ix_auth_external_accounts_user_id", "auth_external_accounts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_external_accounts_user_id", table_name="auth_external_accounts")
    op.drop_table("auth_external_accounts")

