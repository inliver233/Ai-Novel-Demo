"""repair integer datetimes

Revision ID: 09e76a9bafd4
Revises: f0e7b256e514
Create Date: 2026-01-04

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "09e76a9bafd4"
down_revision = "f0e7b256e514"
branch_labels = None
depends_on = None


_TABLES: dict[str, tuple[str, ...]] = {
    "users": ("created_at", "updated_at"),
    "projects": ("created_at", "updated_at"),
    "outlines": ("created_at", "updated_at"),
    "llm_profiles": ("created_at", "updated_at"),
    "chapters": ("updated_at",),
    "characters": ("updated_at",),
    "generation_runs": ("created_at",),
    "prompt_presets": ("created_at", "updated_at"),
    "prompt_blocks": ("created_at", "updated_at"),
    "batch_generation_tasks": ("created_at", "updated_at"),
    "batch_generation_task_items": ("created_at", "updated_at"),
}


def _repair_sql(table: str, column: str) -> list[sa.TextClause]:
    # Some legacy SQLite migrations can coerce ISO strings like
    # "2025-01-01 00:00:00+00:00" into integers (e.g. 2025) when a `CAST(... AS DATETIME)`
    # sneaks into the batch-copy path. SQLAlchemy's SQLite DateTime loader expects a string,
    # so we normalize integers back into a parseable ISO datetime string.
    year_to_iso = f"printf('%04d-01-01 00:00:00+00:00', {column})"
    return [
        sa.text(
            f"""
            UPDATE {table}
            SET {column} = {year_to_iso}
            WHERE typeof({column}) = 'integer'
              AND {column} BETWEEN 1900 AND 2200
            """
        ),
        sa.text(
            f"""
            UPDATE {table}
            SET {column} = printf('%04d-01-01 00:00:00+00:00', CAST({column} AS INTEGER))
            WHERE typeof({column}) = 'real'
              AND {column} BETWEEN 1900 AND 2200
            """
        ),
        # Also normalize text formats that Python's datetime.fromisoformat doesn't accept.
        sa.text(
            f"""
            UPDATE {table}
            SET {column} = replace(replace({column}, 'T', ' '), 'Z', '+00:00')
            WHERE typeof({column}) = 'text'
              AND ({column} LIKE '%T%' OR {column} LIKE '%Z')
            """
        ),
    ]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return

    for table_name, column_names in _TABLES.items():
        for column_name in column_names:
            for stmt in _repair_sql(table_name, column_name):
                conn.execute(stmt)


def downgrade() -> None:
    # Non-reversible: original sub-second precision and timezone fidelity may have been lost
    # if timestamps were already coerced into integers.
    return

