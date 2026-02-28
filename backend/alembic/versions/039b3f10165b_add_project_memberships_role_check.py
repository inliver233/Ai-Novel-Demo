"""add project_memberships.role CHECK constraint

Revision ID: 039b3f10165b
Revises: ea09718bdf1e
Create Date: 2026-01-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "039b3f10165b"
down_revision = "ea09718bdf1e"
branch_labels = None
depends_on = None


def _constraint_exists(name: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        constraints = inspector.get_check_constraints("project_memberships", schema=None)
        return any(str(c.get("name") or "") == name for c in constraints)
    except Exception:
        return False


def upgrade() -> None:
    # Normalize legacy values (case/whitespace) before enforcing the constraint.
    op.execute(sa.text("UPDATE project_memberships SET role = lower(trim(role))"))

    if _constraint_exists("ck_project_memberships_role"):
        return

    with op.batch_alter_table("project_memberships", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_project_memberships_role",
            "role IN ('viewer','editor','owner')",
        )


def downgrade() -> None:
    if not _constraint_exists("ck_project_memberships_role"):
        return
    with op.batch_alter_table("project_memberships", schema=None) as batch_op:
        batch_op.drop_constraint("ck_project_memberships_role", type_="check")
