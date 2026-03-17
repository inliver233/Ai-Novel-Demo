from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.memory_route_structured_helpers import (
    _build_structured_memory_payload,
    _count_structured_memory_rows,
    _list_structured_memory_table_page,
    _normalize_structured_memory_args,
)
from app.core.errors import AppError
from app.db.base import Base
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.project import Project
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryEvent, MemoryForeshadow, MemoryRelation
from app.models.user import User

UTC = timezone.utc


class TestMemoryRouteStructuredHelpers(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            'sqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(
            engine,
            tables=[
                User.__table__,
                Project.__table__,
                Outline.__table__,
                Chapter.__table__,
                MemoryEntity.__table__,
                MemoryRelation.__table__,
                MemoryEvent.__table__,
                MemoryForeshadow.__table__,
                MemoryEvidence.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id='u_owner', display_name='owner'))
            db.add(Project(id='p1', owner_user_id='u_owner', name='Project 1', genre=None, logline=None))
            db.add(Outline(id='o1', project_id='p1', title='Outline', content_md=None, structure_json=None))
            db.add(Chapter(id='c1', project_id='p1', outline_id='o1', number=1, title='Ch1', status='done'))

            entity_old_dt = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
            entity_new_dt = entity_old_dt + timedelta(minutes=5)
            deleted_dt = entity_new_dt + timedelta(minutes=5)
            db.add_all(
                [
                    MemoryEntity(
                        id='e-old',
                        project_id='p1',
                        entity_type='character',
                        name='Alice-A',
                        summary_md='旧摘要',
                        attributes_json='{"role":"hero"}',
                        created_at=entity_old_dt,
                        updated_at=entity_old_dt,
                        deleted_at=None,
                    ),
                    MemoryEntity(
                        id='e-new',
                        project_id='p1',
                        entity_type='character',
                        name='Alice-B',
                        summary_md='新摘要',
                        attributes_json='{"role":"lead"}',
                        created_at=entity_new_dt,
                        updated_at=entity_new_dt,
                        deleted_at=None,
                    ),
                    MemoryEntity(
                        id='e-deleted',
                        project_id='p1',
                        entity_type='character',
                        name='Alice-Deleted',
                        summary_md='已删除',
                        attributes_json=None,
                        created_at=deleted_dt,
                        updated_at=deleted_dt,
                        deleted_at=deleted_dt,
                    ),
                ]
            )

            evidence_old_dt = datetime(2026, 3, 15, 11, 0, tzinfo=UTC)
            evidence_new_dt = evidence_old_dt + timedelta(minutes=5)
            db.add_all(
                [
                    MemoryEvidence(
                        id='ev-old',
                        project_id='p1',
                        source_type='relation',
                        source_id='rel-1',
                        quote_md='old quote',
                        attributes_json='{"kind":"old"}',
                        created_at=evidence_old_dt,
                        deleted_at=None,
                    ),
                    MemoryEvidence(
                        id='ev-new',
                        project_id='p1',
                        source_type='relation',
                        source_id='rel-1',
                        quote_md='new quote',
                        attributes_json='{"kind":"new"}',
                        created_at=evidence_new_dt,
                        deleted_at=None,
                    ),
                ]
            )
            db.commit()

    def test_normalize_structured_memory_args_validates_table_and_before(self) -> None:
        args = _normalize_structured_memory_args(
            table=' entities ',
            q=' Alice ',
            before='2026-03-15T12:00:00Z',
            limit=50,
        )
        self.assertEqual(args.table, 'entities')
        self.assertEqual(args.keyword, 'Alice')
        self.assertEqual(args.pattern, '%Alice%')
        self.assertEqual(args.before_dt.isoformat() if args.before_dt else None, '2026-03-15T12:00:00+00:00')

        with self.assertRaises(AppError):
            _normalize_structured_memory_args(table='unknown', q=None, before=None, limit=10)

        with self.assertRaises(AppError):
            _normalize_structured_memory_args(table='entities', q=None, before='bad-before', limit=10)

    def test_structured_entity_page_filters_counts_and_uses_updated_at_cursor(self) -> None:
        with self.SessionLocal() as db:
            args = _normalize_structured_memory_args(table='entities', q='Alice', before=None, limit=1)
            count = _count_structured_memory_rows(
                db,
                project_id='p1',
                table_name='entities',
                include_deleted=False,
                pattern=args.pattern,
            )
            self.assertEqual(count, 2)

            page1 = _list_structured_memory_table_page(
                db,
                project_id='p1',
                table_name='entities',
                include_deleted=False,
                pattern=args.pattern,
                before_dt=args.before_dt,
                limit=args.limit,
            )
            self.assertEqual([row['id'] for row in page1.items], ['e-new'])
            self.assertEqual(page1.items[0]['attributes'], {'role': 'lead'})
            self.assertEqual(page1.cursor, '2026-03-15T10:05:00+00:00')

            page2_args = _normalize_structured_memory_args(table='entities', q='Alice', before=page1.cursor, limit=1)
            page2 = _list_structured_memory_table_page(
                db,
                project_id='p1',
                table_name='entities',
                include_deleted=False,
                pattern=page2_args.pattern,
                before_dt=page2_args.before_dt,
                limit=page2_args.limit,
            )
            self.assertEqual([row['id'] for row in page2.items], ['e-old'])
            self.assertIsNone(page2.cursor)

    def test_structured_evidence_page_uses_created_at_cursor(self) -> None:
        with self.SessionLocal() as db:
            args = _normalize_structured_memory_args(table='evidence', q='rel-1', before=None, limit=1)
            page1 = _list_structured_memory_table_page(
                db,
                project_id='p1',
                table_name='evidence',
                include_deleted=False,
                pattern=args.pattern,
                before_dt=args.before_dt,
                limit=args.limit,
            )
            self.assertEqual([row['id'] for row in page1.items], ['ev-new'])
            self.assertEqual(page1.items[0]['attributes'], {'kind': 'new'})
            self.assertEqual(page1.cursor, '2026-03-15T11:05:00+00:00')

            page2_args = _normalize_structured_memory_args(table='evidence', q='rel-1', before=page1.cursor, limit=1)
            page2 = _list_structured_memory_table_page(
                db,
                project_id='p1',
                table_name='evidence',
                include_deleted=False,
                pattern=page2_args.pattern,
                before_dt=page2_args.before_dt,
                limit=page2_args.limit,
            )
            self.assertEqual([row['id'] for row in page2.items], ['ev-old'])
            self.assertIsNone(page2.cursor)

    def test_build_structured_memory_payload_keeps_counts_cursor_and_selected_table(self) -> None:
        with self.SessionLocal() as db:
            payload = _build_structured_memory_payload(
                db,
                project_id='p1',
                include_deleted=False,
                table='entities',
                q='Alice',
                before=None,
                limit=1,
            )
            self.assertEqual(payload['table'], 'entities')
            self.assertEqual(payload['q'], 'Alice')
            self.assertEqual((payload['counts'] or {}).get('entities'), 2)
            self.assertEqual([row['id'] for row in payload['entities']], ['e-new'])
            self.assertEqual(payload['relations'], [])
            self.assertEqual((payload['cursor'] or {}).get('entities'), '2026-03-15T10:05:00+00:00')


if __name__ == '__main__':
    unittest.main()
