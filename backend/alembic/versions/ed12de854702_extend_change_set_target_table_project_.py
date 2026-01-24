"""extend_change_set_target_table_project_tables

Revision ID: ed12de854702
Revises: 026e378fe453
Create Date: 2026-01-25 06:22:13.284944

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'ed12de854702'
down_revision = '026e378fe453'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memory_change_set_items", schema=None) as batch_op:
        batch_op.drop_constraint("ck_memory_change_set_items_target_table", type_="check")
        batch_op.create_check_constraint(
            "ck_memory_change_set_items_target_table",
            "target_table IN ('entities','relations','events','foreshadows','evidence','project_table_rows')",
        )


def downgrade() -> None:
    with op.batch_alter_table("memory_change_set_items", schema=None) as batch_op:
        batch_op.drop_constraint("ck_memory_change_set_items_target_table", type_="check")
        batch_op.create_check_constraint(
            "ck_memory_change_set_items_target_table",
            "target_table IN ('entities','relations','events','foreshadows','evidence')",
        )
