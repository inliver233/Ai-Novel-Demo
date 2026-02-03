from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.services.project_task_service import schedule_chapter_done_tasks


class TestTableAutoUpdateTaskScheduling(unittest.TestCase):
    def test_schedule_chapter_done_tasks_schedules_table_ai_update_for_numeric_tables(self) -> None:
        settings = Mock()
        settings.auto_update_worldbook_enabled = False
        settings.auto_update_characters_enabled = False
        settings.auto_update_story_memory_enabled = False
        settings.auto_update_graph_enabled = False
        settings.auto_update_vector_enabled = False
        settings.auto_update_search_enabled = False
        settings.auto_update_fractal_enabled = False
        settings.auto_update_tables_enabled = True

        db = Mock()
        db.get.return_value = settings

        db.execute.return_value.all.return_value = [
            (
                "t-num",
                '{"version":1,"columns":[{"key":"key","type":"string","required":true},{"key":"value","type":"number","required":true}]}',
                True,
            ),
            (
                "t-num-disabled",
                '{"version":1,"columns":[{"key":"key","type":"string","required":true},{"key":"value","type":"number","required":true}]}',
                False,
            ),
            (
                "t-str",
                '{"version":1,"columns":[{"key":"key","type":"string","required":true},{"key":"value","type":"string","required":false}]}',
                True,
            ),
        ]

        with patch("app.services.table_ai_update_service.schedule_table_ai_update_task", return_value="task-num") as sched:
            out = schedule_chapter_done_tasks(
                db=db,
                project_id="p1",
                actor_user_id="u1",
                request_id="rid-test",
                chapter_id="c1",
                chapter_token="2026-02-01T00:00:00Z",
                reason="chapter_done",
            )

        sched.assert_called_once()
        self.assertEqual(out.get("table_ai_update"), "task-num")
