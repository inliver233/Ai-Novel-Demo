"""add writing styles tables

Revision ID: ea09718bdf1e
Revises: 2662fe2e5a01
Create Date: 2026-01-10

"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "ea09718bdf1e"
down_revision = "2662fe2e5a01"
branch_labels = None
depends_on = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def upgrade() -> None:
    op.create_table(
        "writing_styles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_content", sa.Text(), nullable=False),
        sa.Column("is_preset", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("writing_styles", schema=None) as batch_op:
        batch_op.create_index("ix_writing_styles_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_index("ix_writing_styles_is_preset", ["is_preset"], unique=False)

    op.create_table(
        "project_default_styles",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("style_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["style_id"], ["writing_styles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    with op.batch_alter_table("project_default_styles", schema=None) as batch_op:
        batch_op.create_index("ix_project_default_styles_style_id", ["style_id"], unique=False)

    now = _utc_now()
    presets = sa.table(
        "writing_styles",
        sa.column("id", sa.String),
        sa.column("owner_user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("prompt_content", sa.Text),
        sa.column("is_preset", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        presets,
        [
            {
                "id": str(uuid4()),
                "owner_user_id": None,
                "name": "通用（默认）",
                "description": "适配大多数题材：自然中文、少套话、节奏清晰。",
                "prompt_content": "写作要求：\n- 中文自然、克制少套话。\n- 叙事清晰、节奏紧凑。\n- 避免现代网络口水与过度形容词堆叠。\n- 对话符合角色身份与场景。",
                "is_preset": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": str(uuid4()),
                "owner_user_id": None,
                "name": "更克制（简洁）",
                "description": "更少形容与更强信息密度。",
                "prompt_content": "写作要求：\n- 句子更短，信息密度更高。\n- 描写更精确，避免重复与冗余。\n- 优先用动作与细节呈现情绪，而非直接评价。",
                "is_preset": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": str(uuid4()),
                "owner_user_id": None,
                "name": "更有画面（氛围）",
                "description": "强调场景氛围与镜头感，但避免过度堆砌。",
                "prompt_content": "写作要求：\n- 强调镜头感：远景→中景→特写。\n- 用五感描写营造氛围，但避免长段落堆砌形容。\n- 保持人物动机与动作连贯。",
                "is_preset": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("project_default_styles")
    op.drop_table("writing_styles")

