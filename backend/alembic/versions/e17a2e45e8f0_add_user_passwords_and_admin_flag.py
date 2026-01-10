"""add user_passwords and admin flag

Revision ID: e17a2e45e8f0
Revises: ca30c45d18e1
Create Date: 2026-01-10 04:21:40.545092

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'e17a2e45e8f0'
down_revision = 'ca30c45d18e1'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c.get("name") for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    # NOTE: SQLite DDL isn't transactional. If a previous run partially created tables/columns
    # but failed before updating alembic_version, rerunning would crash. Make this migration
    # idempotent (best-effort) to unblock safe restarts.

    if not _has_table("user_passwords"):
        op.create_table(
            "user_passwords",
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id"),
        )

    if _has_table("users") and not _has_column("users", "is_admin"):
        bind = op.get_bind()
        dialect = getattr(getattr(bind, "dialect", None), "name", "")

        # Clean up a common partial-migration artifact for SQLite batch operations.
        # If a previous attempt created `_alembic_tmp_users` but failed before renaming,
        # reruns would crash with "table _alembic_tmp_users already exists".
        if dialect == "sqlite" and _has_table("_alembic_tmp_users"):
            if _has_table("users"):
                op.drop_table("_alembic_tmp_users")
            else:
                op.rename_table("_alembic_tmp_users", "users")

        op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
        if dialect != "sqlite":
            op.alter_column("users", "is_admin", server_default=None)


def downgrade() -> None:
    if _has_table("users") and _has_column("users", "is_admin"):
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.drop_column("is_admin")

    if _has_table("user_passwords"):
        op.drop_table("user_passwords")
