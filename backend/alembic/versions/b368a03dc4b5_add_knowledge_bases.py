"""add knowledge_bases

Revision ID: b368a03dc4b5
Revises: 09930c9ce083
Create Date: 2026-01-19 20:02:04.388729

"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = 'b368a03dc4b5'
down_revision = '09930c9ce083'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'knowledge_bases',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('kb_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'kb_id', name='uq_knowledge_bases_project_id_kb_id'),
    )
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.create_index('ix_knowledge_bases_project_id', ['project_id'], unique=False)
        batch_op.create_index('ix_knowledge_bases_project_id_enabled', ['project_id', 'enabled'], unique=False)
        batch_op.create_index('ix_knowledge_bases_project_id_order_index', ['project_id', 'order_index'], unique=False)

    bind = op.get_bind()
    project_ids = bind.execute(sa.text('SELECT id FROM projects')).scalars().all()
    if not project_ids:
        return

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        {
            'id': str(uuid4()),
            'project_id': str(project_id),
            'kb_id': 'default',
            'name': 'Default',
            'enabled': True,
            'weight': 1.0,
            'order_index': 0,
            'created_at': now,
            'updated_at': now,
        }
        for project_id in project_ids
    ]
    bind.execute(
        sa.text(
            """
            INSERT INTO knowledge_bases (
              id, project_id, kb_id, name, enabled, weight, order_index, created_at, updated_at
            ) VALUES (
              :id, :project_id, :kb_id, :name, :enabled, :weight, :order_index, :created_at, :updated_at
            )
            """.strip()
        ),
        rows,
    )


def downgrade() -> None:
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.drop_index('ix_knowledge_bases_project_id_order_index')
        batch_op.drop_index('ix_knowledge_bases_project_id_enabled')
        batch_op.drop_index('ix_knowledge_bases_project_id')

    op.drop_table('knowledge_bases')
