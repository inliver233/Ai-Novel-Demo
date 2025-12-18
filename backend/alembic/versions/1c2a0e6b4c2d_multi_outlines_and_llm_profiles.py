"""multi outlines and llm profiles

Revision ID: 1c2a0e6b4c2d
Revises: 0f24b611cf21
Create Date: 2025-12-15 00:00:00.000000

"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision = "1c2a0e6b4c2d"
down_revision = "0f24b611cf21"
branch_labels = None
depends_on = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upgrade() -> None:
    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.create_index("ix_llm_profiles_owner_user_id", ["owner_user_id"], unique=False)

    op.create_table(
        "outlines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("structure_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("outlines", schema=None) as batch_op:
        batch_op.create_index("ix_outlines_project_id", ["project_id"], unique=False)

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("active_outline_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("llm_profile_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_projects_active_outline_id",
            "outlines",
            ["active_outline_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_projects_llm_profile_id",
            "llm_profiles",
            ["llm_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_projects_active_outline_id", ["active_outline_id"], unique=False)
        batch_op.create_index("ix_projects_llm_profile_id", ["llm_profile_id"], unique=False)

    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("outline_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_chapters_outline_id",
            "outlines",
            ["outline_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.drop_constraint("uq_chapters_project_id_number", type_="unique")
        batch_op.create_unique_constraint("uq_chapters_outline_id_number", ["outline_id", "number"])
        batch_op.create_index("ix_chapters_outline_id", ["outline_id"], unique=False)

    conn = op.get_bind()
    now = _utc_now_iso()

    project_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM projects")).fetchall()]
    for project_id in project_ids:
        old = conn.execute(
            sa.text("SELECT content_md, updated_at FROM outline WHERE project_id = :pid"),
            {"pid": project_id},
        ).fetchone()
        old_content = (old[0] if old else "") or ""
        old_updated = (old[1] if old and old[1] else now) or now
        outline_id = str(uuid4())

        conn.execute(
            sa.text(
                """
                INSERT INTO outlines (id, project_id, title, content_md, structure_json, created_at, updated_at)
                VALUES (:id, :project_id, :title, :content_md, :structure_json, :created_at, :updated_at)
                """
            ),
            {
                "id": outline_id,
                "project_id": project_id,
                "title": "默认大纲",
                "content_md": old_content,
                "structure_json": None,
                "created_at": old_updated,
                "updated_at": old_updated,
            },
        )
        conn.execute(
            sa.text("UPDATE projects SET active_outline_id = :outline_id WHERE id = :project_id"),
            {"outline_id": outline_id, "project_id": project_id},
        )
        conn.execute(
            sa.text("UPDATE chapters SET outline_id = :outline_id WHERE project_id = :project_id"),
            {"outline_id": outline_id, "project_id": project_id},
        )

    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.alter_column("outline_id", existing_type=sa.String(length=36), nullable=False)

    op.drop_table("outline")


def downgrade() -> None:
    op.create_table(
        "outline",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    conn = op.get_bind()
    now = _utc_now_iso()
    project_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM projects")).fetchall()]
    for project_id in project_ids:
        active = conn.execute(
            sa.text("SELECT active_outline_id FROM projects WHERE id = :pid"),
            {"pid": project_id},
        ).fetchone()
        outline_id = active[0] if active else None
        if not outline_id:
            continue
        row = conn.execute(
            sa.text("SELECT content_md, updated_at FROM outlines WHERE id = :oid"),
            {"oid": outline_id},
        ).fetchone()
        content_md = (row[0] if row else "") or ""
        updated_at = (row[1] if row and row[1] else now) or now
        conn.execute(
            sa.text("INSERT INTO outline (project_id, content_md, updated_at) VALUES (:pid, :content, :updated)"),
            {"pid": project_id, "content": content_md, "updated": updated_at},
        )

    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.drop_index("ix_chapters_outline_id")
        batch_op.drop_constraint("uq_chapters_outline_id_number", type_="unique")
        batch_op.create_unique_constraint("uq_chapters_project_id_number", ["project_id", "number"])
        batch_op.drop_constraint("fk_chapters_outline_id", type_="foreignkey")
        batch_op.drop_column("outline_id")

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index("ix_projects_active_outline_id")
        batch_op.drop_index("ix_projects_llm_profile_id")
        batch_op.drop_constraint("fk_projects_active_outline_id", type_="foreignkey")
        batch_op.drop_constraint("fk_projects_llm_profile_id", type_="foreignkey")
        batch_op.drop_column("llm_profile_id")
        batch_op.drop_column("active_outline_id")

    with op.batch_alter_table("outlines", schema=None) as batch_op:
        batch_op.drop_index("ix_outlines_project_id")
    op.drop_table("outlines")

    with op.batch_alter_table("llm_profiles", schema=None) as batch_op:
        batch_op.drop_index("ix_llm_profiles_owner_user_id")
    op.drop_table("llm_profiles")
