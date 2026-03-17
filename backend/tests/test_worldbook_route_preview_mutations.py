from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.worldbook_route_mutations import (
    _build_worldbook_create_payload,
    _build_worldbook_delete_payload,
    _build_worldbook_update_payload,
)
from app.api.routes.worldbook_route_preview import (
    _build_worldbook_auto_update_payload,
    _build_worldbook_preview_payload,
)
from app.core.config import settings
from app.core.errors import AppError
from app.db.base import Base
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook import WorldBookEntryCreate, WorldBookEntryUpdate, WorldBookPreviewTriggerRequest


class TestWorldbookRoutePreviewMutations(unittest.TestCase):
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
                Outline.__table__,
                Chapter.__table__,
                WorldBookEntry.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(Outline(id='outline-1', project_id='project-1', title='Outline 1'))
            db.commit()

    def test_auto_update_payload_resolves_latest_done_and_returns_task_linkage(self) -> None:
        with self.SessionLocal() as db:
            db.add_all(
                [
                    Chapter(
                        id='chapter-done',
                        project_id='project-1',
                        outline_id='outline-1',
                        number=1,
                        title='Done',
                        plan='',
                        content_md='',
                        summary='',
                        status='done',
                    ),
                    Chapter(
                        id='chapter-drafting',
                        project_id='project-1',
                        outline_id='outline-1',
                        number=2,
                        title='Drafting',
                        plan='',
                        content_md='',
                        summary='',
                        status='drafting',
                    ),
                ]
            )
            db.commit()

            with patch(
                'app.api.routes.worldbook_route_preview.schedule_worldbook_auto_update_task',
                return_value='task-1',
            ) as sched:
                payload = _build_worldbook_auto_update_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-auto',
                    chapter_id=None,
                )

        self.assertEqual(payload, {'task_id': 'task-1', 'chapter_id': 'chapter-done'})
        self.assertEqual(sched.call_args.kwargs['reason'], 'manual_worldbook_auto_update')
        self.assertEqual(sched.call_args.kwargs['chapter_id'], 'chapter-done')
        self.assertTrue(str(sched.call_args.kwargs['chapter_token']).strip())

    def test_auto_update_payload_rejects_not_done_explicit_chapter(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                Chapter(
                    id='chapter-drafting',
                    project_id='project-1',
                    outline_id='outline-1',
                    number=2,
                    title='Drafting',
                    plan='',
                    content_md='',
                    summary='',
                    status='drafting',
                )
            )
            db.commit()

            with self.assertRaises(AppError) as ctx:
                _build_worldbook_auto_update_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-auto-fail',
                    chapter_id='chapter-drafting',
                )

        self.assertEqual((ctx.exception.details or {}).get('reason'), 'chapter_not_done')

    def test_preview_payload_includes_preprocess_and_match_config(self) -> None:
        original_flags = {
            'alias': getattr(settings, 'worldbook_match_alias_enabled', False),
            'pinyin': getattr(settings, 'worldbook_match_pinyin_enabled', False),
            'regex': getattr(settings, 'worldbook_match_regex_enabled', False),
            'allowlist': getattr(settings, 'worldbook_match_regex_allowlist_json', None),
            'max_entries': getattr(settings, 'worldbook_match_max_triggered_entries', 0),
        }
        try:
            settings.worldbook_match_alias_enabled = True
            settings.worldbook_match_pinyin_enabled = False
            settings.worldbook_match_regex_enabled = True
            settings.worldbook_match_regex_allowlist_json = json.dumps(['dragon\\d+'])
            settings.worldbook_match_max_triggered_entries = 7

            with self.SessionLocal() as db:
                db.add(
                    ProjectSettings(
                        project_id='project-1',
                        query_preprocessing_json=json.dumps(
                            {
                                'enabled': True,
                                'tags': ['hero'],
                                'exclusion_rules': ['ban'],
                                'index_ref_enhance': True,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                db.add(
                    WorldBookEntry(
                        id='wb-1',
                        project_id='project-1',
                        title='Dragon',
                        content_md='Dragon content',
                        enabled=True,
                        constant=False,
                        keywords_json=json.dumps(['dragon'], ensure_ascii=False),
                        exclude_recursion=False,
                        prevent_recursion=False,
                        char_limit=12000,
                        priority='important',
                    )
                )
                db.commit()

                body = WorldBookPreviewTriggerRequest.model_validate(
                    {
                        'query_text': '#hero dragon ban 第12章',
                        'include_constant': True,
                        'enable_recursion': True,
                        'char_limit': 9999,
                    }
                )
                payload = _build_worldbook_preview_payload(db, project_id='project-1', body=body)
        finally:
            settings.worldbook_match_alias_enabled = original_flags['alias']
            settings.worldbook_match_pinyin_enabled = original_flags['pinyin']
            settings.worldbook_match_regex_enabled = original_flags['regex']
            settings.worldbook_match_regex_allowlist_json = original_flags['allowlist']
            settings.worldbook_match_max_triggered_entries = original_flags['max_entries']

        self.assertEqual(payload['raw_query_text'], '#hero dragon ban 第12章')
        self.assertIn('chapter:12', payload['normalized_query_text'])
        self.assertNotIn('#hero', payload['normalized_query_text'])
        self.assertIn('hero', payload['preprocess_obs']['extracted_tags'])
        self.assertIn('ban', payload['preprocess_obs']['applied_exclusion_rules'])
        self.assertEqual(payload['match_config']['alias_enabled'], True)
        self.assertEqual(payload['match_config']['regex_enabled'], True)
        self.assertEqual(payload['match_config']['regex_allowlist_size'], 1)
        self.assertEqual(payload['match_config']['max_triggered_entries'], 7)
        self.assertEqual(payload['triggered'][0]['reason'], 'keyword:dragon')

    def test_create_update_delete_payloads_normalize_keywords_and_schedule_reasons(self) -> None:
        with self.SessionLocal() as db:
            create_body = WorldBookEntryCreate.model_validate(
                {
                    'title': 'Alpha',
                    'content_md': 'before',
                    'enabled': True,
                    'constant': False,
                    'keywords': [' alpha ', 'beta'],
                    'exclude_recursion': False,
                    'prevent_recursion': False,
                    'char_limit': 12000,
                    'priority': 'important',
                }
            )
            with patch(
                'app.api.routes.worldbook_route_mutations.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_mutations.schedule_search_rebuild_task'
            ) as search_sched:
                created = _build_worldbook_create_payload(
                    db,
                    project_id='project-1',
                    actor_user_id='user-1',
                    request_id='rid-create',
                    body=create_body,
                )
                self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_create')
                self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_create')

            created_id = created['worldbook_entry']['id']
            self.assertEqual(created['worldbook_entry']['keywords'], ['alpha', 'beta'])

            row = db.get(WorldBookEntry, created_id)
            self.assertIsNotNone(row)
            assert row is not None
            update_body = WorldBookEntryUpdate.model_validate(
                {
                    'content_md': 'after',
                    'enabled': False,
                    'keywords': [' gamma '],
                    'char_limit': 99,
                    'priority': 'must',
                }
            )
            with patch(
                'app.api.routes.worldbook_route_mutations.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_mutations.schedule_search_rebuild_task'
            ) as search_sched:
                updated = _build_worldbook_update_payload(
                    db,
                    row=row,
                    actor_user_id='user-1',
                    request_id='rid-update',
                    body=update_body,
                )
                self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_update')
                self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_update')

            self.assertEqual(updated['worldbook_entry']['content_md'], 'after')
            self.assertEqual(updated['worldbook_entry']['keywords'], ['gamma'])
            self.assertEqual(updated['worldbook_entry']['priority'], 'must')

            row = db.get(WorldBookEntry, created_id)
            self.assertIsNotNone(row)
            assert row is not None
            with patch(
                'app.api.routes.worldbook_route_mutations.schedule_vector_rebuild_task'
            ) as vector_sched, patch(
                'app.api.routes.worldbook_route_mutations.schedule_search_rebuild_task'
            ) as search_sched:
                deleted = _build_worldbook_delete_payload(
                    db,
                    row=row,
                    actor_user_id='user-1',
                    request_id='rid-delete',
                )
                self.assertEqual(vector_sched.call_args.kwargs['reason'], 'worldbook_delete')
                self.assertEqual(search_sched.call_args.kwargs['reason'], 'worldbook_delete')

            self.assertEqual(deleted, {})
            self.assertIsNone(db.get(WorldBookEntry, created_id))
            settings_row = db.get(ProjectSettings, 'project-1')
            self.assertIsNotNone(settings_row)
            assert settings_row is not None
            self.assertTrue(settings_row.vector_index_dirty)


if __name__ == '__main__':
    unittest.main()
