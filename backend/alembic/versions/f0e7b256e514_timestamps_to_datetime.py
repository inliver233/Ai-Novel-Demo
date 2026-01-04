"""timestamps to datetime

Revision ID: f0e7b256e514
Revises: dfb3c3ed0847
Create Date: 2026-01-04 17:19:52.734536

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'f0e7b256e514'
down_revision = 'dfb3c3ed0847'
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


def _iso_z_to_iso_offset_sql(column_ref: str) -> str:
    # sqlite's DateTime parsing relies on Python's `datetime.fromisoformat`,
    # which does not accept the "Z" suffix. Convert:
    #   2026-01-03T20:39:54Z -> 2026-01-03 20:39:54+00:00
    return f"replace(replace({column_ref}, 'T', ' '), 'Z', '+00:00')"


def _iso_offset_to_iso_z_sql(column_ref: str) -> str:
    return f"replace(replace({column_ref}, ' ', 'T'), '+00:00', 'Z')"


def upgrade() -> None:
    conn = op.get_bind()

    if conn.dialect.name == "sqlite":
        # Avoid Alembic's batch-migrate CAST() for DateTime on SQLite which may
        # coerce ISO strings like "2026-01-03 ..." into integers (e.g. 2026).
        # Instead, add new DateTime columns, copy normalized text, then swap.
        for table_name, column_names in _TABLES.items():
            for column_name in column_names:
                tmp = f"{column_name}__dt"
                op.add_column(table_name, sa.Column(tmp, sa.DateTime(timezone=True), nullable=True))
                conn.execute(
                    sa.text(
                        f"""
                        UPDATE {table_name}
                        SET {tmp} = {_iso_z_to_iso_offset_sql(column_name)}
                        WHERE {column_name} IS NOT NULL
                        """
                    )
                )
                # Defensive: enforce non-null when the original column is non-null.
                conn.execute(
                    sa.text(
                        f"""
                        UPDATE {table_name}
                        SET {tmp} = {_iso_z_to_iso_offset_sql(column_name)}
                        WHERE {tmp} IS NULL AND {column_name} IS NOT NULL
                        """
                    )
                )

        for table_name, column_names in _TABLES.items():
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                for column_name in column_names:
                    tmp = f"{column_name}__dt"
                    batch_op.drop_column(column_name, existing_type=sa.String(length=32))
                    batch_op.alter_column(
                        tmp,
                        new_column_name=column_name,
                        existing_type=sa.DateTime(timezone=True),
                        existing_nullable=True,
                        nullable=False,
                    )
        return

    # non-sqlite: normalize and then alter types in-place.
    for table_name, column_names in _TABLES.items():
        for column_name in column_names:
            conn.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET {column_name} = {_iso_z_to_iso_offset_sql(column_name)}
                    WHERE {column_name} IS NOT NULL
                      AND ({column_name} LIKE '%T%' OR {column_name} LIKE '%Z')
                    """
                )
            )
            alter_kwargs: dict[str, object] = {}
            if conn.dialect.name == "postgresql":
                alter_kwargs["postgresql_using"] = f"{column_name}::timestamptz"

            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.String(length=32),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
                **alter_kwargs,
            )


def downgrade() -> None:
    conn = op.get_bind()

    if conn.dialect.name == "sqlite":
        for table_name, column_names in _TABLES.items():
            for column_name in column_names:
                tmp = f"{column_name}__str"
                op.add_column(table_name, sa.Column(tmp, sa.String(length=32), nullable=True))
                conn.execute(
                    sa.text(
                        f"""
                        UPDATE {table_name}
                        SET {tmp} = {_iso_offset_to_iso_z_sql(column_name)}
                        WHERE {column_name} IS NOT NULL
                        """
                    )
                )
                conn.execute(
                    sa.text(
                        f"""
                        UPDATE {table_name}
                        SET {tmp} = {_iso_offset_to_iso_z_sql(column_name)}
                        WHERE {tmp} IS NULL AND {column_name} IS NOT NULL
                        """
                    )
                )

        for table_name, column_names in _TABLES.items():
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                for column_name in column_names:
                    tmp = f"{column_name}__str"
                    batch_op.drop_column(column_name, existing_type=sa.DateTime(timezone=True))
                    batch_op.alter_column(
                        tmp,
                        new_column_name=column_name,
                        existing_type=sa.String(length=32),
                        existing_nullable=True,
                        nullable=False,
                    )
        return

    for table_name, column_names in _TABLES.items():
        for column_name in column_names:
            alter_kwargs: dict[str, object] = {}
            if conn.dialect.name == "postgresql":
                alter_kwargs["postgresql_using"] = f"{column_name}::text"

            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.String(length=32),
                existing_nullable=False,
                **alter_kwargs,
            )
            conn.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET {column_name} = {_iso_offset_to_iso_z_sql(column_name)}
                    WHERE {column_name} IS NOT NULL
                    """
                )
            )
