from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.worldbook_route_helpers import _build_worldbook_entries_payload
from app.api.routes.worldbook_route_import_export import (
    _build_worldbook_export_payload,
    _build_worldbook_import_payload,
)
from app.api.routes.worldbook_route_mutations import (
    _build_worldbook_bulk_delete_payload,
    _build_worldbook_bulk_update_payload,
    _build_worldbook_duplicate_payload,
)
from app.core.errors import AppError
from app.db.base import Base
from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook import (
    WorldBookBulkDeleteRequest,
    WorldBookBulkUpdateRequest,
    WorldBookDuplicateRequest,
    WorldBookImportAllRequest,
)


class TestWorldbookRouteImportExport(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            'sqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)'))
            conn.execute(text("INSERT INTO projects (id) VALUES ('project-1')"))
        Base.metadata.create_all(
            engine,
            tables=[
                ProjectSettings.__table__,
                WorldBookEntry.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def test_list_and_export_payload_map_keywords(self) -> None:
        with self.SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id='wb-1',
                        project_id='project-1',
                        title='Dragon',
                        content_md='Fire',
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps([' dragon ', 'wyrm'], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    ),
                    WorldBookEntry(
                        id='wb-2',
                        project_id='project-1',
                        title='Castle',
                        content_md='Stone',
                        enabled=False,
                        constant=True,
                        keywords_json='[]',
                        exclude_recursion=True,
                        prevent_recursion=True,
                        char_limit=777,
                        priority='must',
                    ),
                ]
            )
            db.commit()

            list_payload = _build_worldbook_entries_payload(db, project_id='project-1')
            export_payload = _build_worldbook_export_payload(db, project_id='project-1')

        self.assertEqual(len(list_payload['worldbook_entries']), 2)
        by_title = {item['title']: item for item in list_payload['worldbook_entries']}
        self.assertEqual(by_title['Dragon']['keywords'], ['dragon', 'wyrm'])
        self.assertTrue(by_title['Castle']['constant'])
        self.assertEqual(export_payload['export']['schema_version'], 'worldbook_export_all_v1')
        exported = {item['title']: item for item in export_payload['export']['entries']}
        self.assertEqual(exported['Dragon']['keywords'], ['dragon', 'wyrm'])
        self.assertEqual(exported['Castle']['char_limit'], 777)

    def test_import_payload_tracks_conflicts_and_apply_merge(self) -> None:
        with self.SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id='dup-1',
                        project_id='project-1',
                        title='Duplicate',
                        content_md='old-1',
                        enabled=True,
                        constant=False,
                        keywords_json='[]',
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    ),
                    WorldBookEntry(
                        id='dup-2',
                        project_id='project-1',
                        title='Duplicate',
                        content_md='old-2',
                        enabled=True,
                        constant=False,
                        keywords_json='[]',
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    ),
                    WorldBookEntry(
                        id='existing-1',
                        project_id='project-1',
                        title='Existing',
                        content_md='before',
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(['legacy'], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    ),
                ]
            )
            db.commit()

            body = WorldBookImportAllRequest.model_validate(
                {
                    'schema_version': 'worldbook_export_all_v1',
                    'dry_run': True,
                    'mode': 'merge',
                    'entries': [
                        {
                            'title': 'Duplicate',
                            'content_md': 'skip',
                            'enabled': True,
                            'constant': False,
                            'keywords': ['dup'],
                            'exclude_recursion': False,
                            'prevent_recursion': False,
                            'char_limit': 12000,
                            'priority': 'important',
                        },
                        {
                            'title': 'Existing',
                            'content_md': 'after',
                            'enabled': False,
                            'constant': True,
                            'keywords': [' updated ', 'existing'],
                            'exclude_recursion': True,
                            'prevent_recursion': True,
                            'char_limit': 321,
                            'priority': 'must',
                        },
                        {
                            'title': 'Created',
                            'content_md': 'new',
                            'enabled': True,
                            'constant': False,
                            'keywords': ['new'],
                            'exclude_recursion': False,
                            'prevent_recursion': False,
                            'char_limit': 12000,
                            'priority': 'optional',
                        },
                    ],
                }
            )
            dry_run = _build_worldbook_import_payload(
                db,
                project_id='project-1',
                actor_user_id='user-1',
                request_id='rid-dry',
                body=body,
            )
            self.assertTrue(dry_run['dry_run'])
            self.assertEqual(dry_run['created'], 1)
            self.assertEqual(dry_run['updated'], 1)
            self.assertEqual(dry_run['skipped'], 1)
            self.assertEqual(len(dry_run['conflicts']), 1)

            apply_body = body.model_copy(update={'dry_run': False})
            with patch(
                'app.api.routes.worldbook_route_import_export.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_import_export.schedule_search_rebuild_task'
            ) as search_sched:
                applied = _build_worldbook_import_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-apply',
                    body=apply_body,
                )

        self.assertFalse(applied['dry_run'])
        self.assertEqual(applied['created'], 1)
        self.assertEqual(applied['updated'], 1)
        self.assertEqual(applied['skipped'], 1)
        self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_import')
        self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_import')

        with self.SessionLocal() as db:
            existing = db.get(WorldBookEntry, 'existing-1')
            self.assertIsNotNone(existing)
            assert existing is not None
            self.assertEqual(existing.content_md, 'after')
            self.assertFalse(existing.enabled)
            self.assertTrue(existing.constant)
            self.assertEqual(existing.keywords_json, json.dumps(['updated', 'existing'], ensure_ascii=False))
            self.assertEqual(existing.char_limit, 321)
            self.assertEqual(existing.priority, 'must')
            created = (
                db.execute(
                    select(WorldBookEntry).where(
                        WorldBookEntry.project_id == 'project-1',
                        WorldBookEntry.title == 'Created',
                    )
                )
                .scalars()
                .one()
            )
            self.assertEqual(created.priority, 'optional')
            settings = db.get(ProjectSettings, 'project-1')
            self.assertIsNotNone(settings)
            assert settings is not None
            self.assertTrue(settings.vector_index_dirty)

    def test_import_payload_overwrite_tracks_delete_all_and_removes_rows(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                WorldBookEntry(
                    id='wb-keep',
                    project_id='project-1',
                    title='Legacy',
                    content_md='legacy',
                    enabled=True,
                    constant=False,
                    keywords_json='[]',
                    exclude_recursion=False,
                    prevent_recursion=False,
                    char_limit=12000,
                    priority='important',
                )
            )
            db.commit()

            body = WorldBookImportAllRequest.model_validate(
                {
                    'schema_version': 'worldbook_export_all_v1',
                    'dry_run': False,
                    'mode': 'overwrite',
                    'entries': [],
                }
            )
            with patch(
                'app.api.routes.worldbook_route_import_export.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_import_export.schedule_search_rebuild_task'
            ) as search_sched:
                payload = _build_worldbook_import_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-overwrite',
                    body=body,
                )

        self.assertEqual(payload['deleted'], 1)
        self.assertEqual(payload['actions'][0]['action'], 'delete_all')
        self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_import')
        self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_import')

        with self.SessionLocal() as db:
            remaining = db.execute(select(WorldBookEntry)).scalars().all()
            self.assertEqual(remaining, [])

    def test_bulk_update_duplicate_and_delete_payloads_preserve_order(self) -> None:
        with self.SessionLocal() as db:
            db.add_all(
                [
                    WorldBookEntry(
                        id='wb-1',
                        project_id='project-1',
                        title='Alpha',
                        content_md='alpha',
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(['alpha'], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    ),
                    WorldBookEntry(
                        id='wb-2',
                        project_id='project-1',
                        title='Beta',
                        content_md='beta',
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(['beta'], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    ),
                ]
            )
            db.commit()

            update_body = WorldBookBulkUpdateRequest.model_validate(
                {
                    'entry_ids': ['wb-2', 'wb-1'],
                    'enabled': False,
                    'constant': True,
                    'prevent_recursion': True,
                    'char_limit': 456,
                    'priority': 'must',
                }
            )
            with patch(
                'app.api.routes.worldbook_route_mutations.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_mutations.schedule_search_rebuild_task'
            ) as search_sched:
                updated = _build_worldbook_bulk_update_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-bulk-update',
                    body=update_body,
                )
                self.assertEqual([item['id'] for item in updated['worldbook_entries']], ['wb-2', 'wb-1'])
                self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_bulk_update')
                self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_bulk_update')

            duplicate_body = WorldBookDuplicateRequest.model_validate({'entry_ids': ['wb-1']})
            with patch(
                'app.api.routes.worldbook_route_mutations.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_mutations.schedule_search_rebuild_task'
            ) as search_sched:
                duplicated = _build_worldbook_duplicate_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-duplicate',
                    body=duplicate_body,
                )
                self.assertEqual(len(duplicated['worldbook_entries']), 1)
                self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_duplicate')
                self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_duplicate')

            delete_body = WorldBookBulkDeleteRequest.model_validate({'entry_ids': ['wb-2', 'wb-1']})
            with patch(
                'app.api.routes.worldbook_route_mutations.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_mutations.schedule_search_rebuild_task'
            ) as search_sched:
                deleted = _build_worldbook_bulk_delete_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-bulk-delete',
                    body=delete_body,
                )
                self.assertEqual(deleted['deleted_ids'], ['wb-2', 'wb-1'])
                self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_bulk_delete')
                self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_bulk_delete')

        self.assertTrue(duplicated['worldbook_entries'][0]['title'].endswith('（复制）'))
        with self.SessionLocal() as db:
            titles = [row.title for row in db.execute(select(WorldBookEntry).order_by(WorldBookEntry.title)).scalars().all()]
            self.assertEqual(titles, ['Alpha（复制）'])

    def test_bulk_update_rejects_missing_ids(self) -> None:
        with self.SessionLocal() as db:
            body = WorldBookBulkUpdateRequest.model_validate(
                {
                    'entry_ids': ['missing-id'],
                    'enabled': False,
                }
            )
            with self.assertRaises(AppError) as ctx:
                _build_worldbook_bulk_update_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-missing',
                    body=body,
                )

        self.assertEqual((ctx.exception.details or {}).get('missing_ids'), ['missing-id'])

    def test_bulk_update_requires_at_least_one_field(self) -> None:
        with self.SessionLocal() as db:
            body = WorldBookBulkUpdateRequest.model_validate({'entry_ids': ['wb-1']})
            with self.assertRaises(AppError) as ctx:
                _build_worldbook_bulk_update_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-empty-patch',
                    body=body,
                )

        self.assertEqual(ctx.exception.message, '至少提供一个更新字段')


if __name__ == '__main__':
    unittest.main()
