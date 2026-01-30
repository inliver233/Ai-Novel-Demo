"""add_search_index_tables

Revision ID: c036de4694b3
Revises: 902bd83f86ed
Create Date: 2026-01-30 19:41:23.769502

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'c036de4694b3'
down_revision = '902bd83f86ed'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("url_path", sa.String(length=512), nullable=True),
        sa.Column("locator_json", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            name="uq_search_documents_project_id_source_type_source_id",
        ),
    )
    with op.batch_alter_table("search_documents", schema=None) as batch_op:
        batch_op.create_index("ix_search_documents_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_search_documents_project_id_source_type", ["project_id", "source_type"], unique=False)

    bind = op.get_bind()
    if getattr(getattr(bind, "dialect", None), "name", "") == "sqlite":
        # NOTE: trigram tokenizer availability is build-dependent. Provide a migration-time fallback so schema upgrades
        # never get blocked by missing extensions.
        try:
            op.execute(
                "CREATE VIRTUAL TABLE search_index USING fts5("
                "title,content,"
                "content='search_documents',content_rowid='id',"
                "tokenize='trigram'"
                ")"
            )
        except Exception:
            op.execute(
                "CREATE VIRTUAL TABLE search_index USING fts5("
                "title,content,"
                "content='search_documents',content_rowid='id',"
                "tokenize='unicode61',"
                "prefix='2 3 4'"
                ")"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if getattr(getattr(bind, "dialect", None), "name", "") == "sqlite":
        op.execute("DROP TABLE IF EXISTS search_index")

    with op.batch_alter_table("search_documents", schema=None) as batch_op:
        batch_op.drop_index("ix_search_documents_project_id_source_type")
        batch_op.drop_index("ix_search_documents_project_id")
    op.drop_table("search_documents")
