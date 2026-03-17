from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.table_route_helpers import (
    _build_project_tables_payload,
    _create_project_table_row_payload,
    _require_project_table,
    _schedule_project_table_ai_update_payload,
    _update_project_table_payload,
)
from app.core.errors import AppError
from app.db.base import Base
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.user import User


class TestTableRouteHelpers(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(
            engine,
            tables=[
                User.__table__,
                Project.__table__,
                ProjectTable.__table__,
                ProjectTableRow.__table__,
                Chapter.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1"))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_list_payload_can_seed_defaults_and_counts_rows(self) -> None:
        with self.SessionLocal() as db:
            payload = _build_project_tables_payload(
                db,
                project_id="p1",
                include_schema=True,
                seed_defaults=True,
            )

        tables = payload["tables"]
        self.assertGreaterEqual(len(tables), 4)
        money = next((table for table in tables if table.get("table_key") == "tbl_money"), None)
        self.assertIsNotNone(money)
        self.assertGreaterEqual(int((money or {}).get("row_count") or 0), 1)
        self.assertIn("schema", money or {})

    def test_update_payload_rejects_incompatible_schema_change(self) -> None:
        with self.SessionLocal() as db:
            table = ProjectTable(
                id="t1",
                project_id="p1",
                table_key="tbl_items",
                name="Items",
                auto_update_enabled=True,
                schema_version=1,
                schema_json=json.dumps(
                    {
                        "version": 1,
                        "columns": [
                            {"key": "key", "type": "string", "required": True},
                            {"key": "value", "type": "string", "required": True},
                        ],
                    },
                    ensure_ascii=False,
                ),
            )
            row = ProjectTableRow(
                id="r1",
                project_id="p1",
                table_id="t1",
                row_index=1,
                data_json=json.dumps({"key": "gold", "value": "10"}, ensure_ascii=False),
            )
            db.add_all([table, row])
            db.commit()

            body = type("Body", (), {"name": None, "auto_update_enabled": None, "table_schema": {"version": 1, "columns": [{"key": "key", "type": "string", "required": True}]}})()
            with self.assertRaises(AppError) as ctx:
                _update_project_table_payload(db, table=table, body=body)

        self.assertEqual(ctx.exception.message, "schema 更新会导致现有行不兼容")
        self.assertEqual((ctx.exception.details or {}).get("row_id"), "r1")

    def test_create_row_payload_uses_next_row_index(self) -> None:
        with self.SessionLocal() as db:
            table = ProjectTable(
                id="t1",
                project_id="p1",
                table_key="tbl_items",
                name="Items",
                auto_update_enabled=True,
                schema_version=1,
                schema_json=json.dumps(
                    {
                        "version": 1,
                        "columns": [
                            {"key": "key", "type": "string", "required": True},
                            {"key": "value", "type": "number", "required": True},
                        ],
                    },
                    ensure_ascii=False,
                ),
            )
            existing = ProjectTableRow(
                id="r1",
                project_id="p1",
                table_id="t1",
                row_index=3,
                data_json=json.dumps({"key": "gold", "value": 10}, ensure_ascii=False),
            )
            db.add_all([table, existing])
            db.commit()

            payload = _create_project_table_row_payload(
                db,
                project_id="p1",
                table=table,
                body=type("Body", (), {"data": {"key": "silver", "value": 5}})(),
            )

        self.assertEqual(payload["row"]["row_index"], 4)
        self.assertEqual(payload["row"]["data"]["key"], "silver")

    def test_schedule_payload_resolves_latest_done_chapter_and_returns_task_linkage(self) -> None:
        with self.SessionLocal() as db:
            table = ProjectTable(
                id="t1",
                project_id="p1",
                table_key="tbl_items",
                name="Items",
                auto_update_enabled=True,
                schema_version=1,
                schema_json='{"version":1,"columns":[]}',
            )
            db.add(table)
            db.add_all(
                [
                    Chapter(
                        id="c1",
                        project_id="p1",
                        outline_id="o1",
                        number=1,
                        title="One",
                        plan="",
                        content_md="",
                        summary="",
                        status="done",
                    ),
                    Chapter(
                        id="c2",
                        project_id="p1",
                        outline_id="o1",
                        number=2,
                        title="Two",
                        plan="",
                        content_md="",
                        summary="",
                        status="drafting",
                    ),
                ]
            )
            db.commit()
            table = _require_project_table(db, project_id="p1", table_id="t1")

            with patch("app.api.routes.table_route_helpers.schedule_table_ai_update_task", return_value="task-1") as sched:
                payload = _schedule_project_table_ai_update_payload(
                    db,
                    project_id="p1",
                    actor_user_id="u1",
                    request_id="rid-test",
                    table=table,
                    focus="focus",
                    chapter_id=None,
                )

        self.assertEqual(payload, {"task_id": "task-1", "chapter_id": "c1", "table_id": "t1"})
        kwargs = sched.call_args.kwargs
        self.assertEqual(kwargs["chapter_id"], "c1")
        self.assertTrue(str(kwargs["chapter_token"]).strip())

    def test_schedule_payload_rejects_not_done_explicit_chapter(self) -> None:
        with self.SessionLocal() as db:
            table = ProjectTable(
                id="t1",
                project_id="p1",
                table_key="tbl_items",
                name="Items",
                auto_update_enabled=True,
                schema_version=1,
                schema_json='{"version":1,"columns":[]}',
            )
            chapter = Chapter(
                id="c1",
                project_id="p1",
                outline_id="o1",
                number=1,
                title="One",
                plan="",
                content_md="",
                summary="",
                status="drafting",
            )
            db.add_all([table, chapter])
            db.commit()
            table = _require_project_table(db, project_id="p1", table_id="t1")

            with self.assertRaises(AppError) as ctx:
                _schedule_project_table_ai_update_payload(
                    db,
                    project_id="p1",
                    actor_user_id="u1",
                    request_id="rid-test",
                    table=table,
                    focus=None,
                    chapter_id="c1",
                )

        self.assertEqual((ctx.exception.details or {}).get("reason"), "chapter_not_done")


if __name__ == "__main__":
    unittest.main()
