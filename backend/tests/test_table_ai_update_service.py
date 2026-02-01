from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.generation_run import GenerationRun
from app.models.project import Project
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.structured_memory import MemoryChangeSet, MemoryChangeSetItem
from app.models.user import User
from app.services.memory_update_service import propose_project_table_change_set
from app.services.table_executor import TableUpdateV1Request


def _compact_json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TestTableAiUpdateService(unittest.TestCase):
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
                GenerationRun.__table__,
                MemoryChangeSet.__table__,
                MemoryChangeSetItem.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="P1", genre=None, logline=None))

            schema = {
                "version": 1,
                "columns": [
                    {"key": "key", "type": "string", "label": "Key", "required": True},
                    {"key": "value", "type": "string", "label": "Value", "required": False},
                ],
            }
            db.add(
                ProjectTable(
                    id="t1",
                    project_id="p1",
                    table_key="tbl_money",
                    name="Money",
                    schema_version=1,
                    schema_json=_compact_json_dumps(schema),
                )
            )
            db.add(
                ProjectTableRow(
                    id="r1",
                    project_id="p1",
                    table_id="t1",
                    row_index=0,
                    data_json=_compact_json_dumps({"key": "gold", "value": "50"}),
                )
            )
            db.commit()

    def test_propose_project_table_change_set_resolves_kv_upsert_by_key_when_row_id_missing(self) -> None:
        with self.SessionLocal() as db:
            payload = TableUpdateV1Request(
                schema_version="table_update_v1",
                idempotency_key="idem-12345678",
                title="Update gold",
                ops=[
                    {
                        "op": "upsert",
                        "table_id": "t1",
                        "row_id": None,
                        "data": {"key": "gold", "value": "100"},
                    }
                ],
            )
            out = propose_project_table_change_set(
                db=db,
                request_id="rid-test",
                actor_user_id="u1",
                project_id="p1",
                payload=payload,
            )

            self.assertEqual(len(out.get("items") or []), 1)
            item = out["items"][0]
            self.assertEqual(item.get("target_table"), "project_table_rows")
            self.assertEqual(item.get("target_id"), "r1")

            before = json.loads(item.get("before_json") or "{}")
            self.assertEqual(before.get("id"), "r1")
            after = json.loads(item.get("after_json") or "{}")
            self.assertEqual(after.get("data", {}).get("key"), "gold")
            self.assertEqual(after.get("data", {}).get("value"), "100")

    def test_propose_project_table_change_set_resolves_kv_upsert_for_numeric_value_schema(self) -> None:
        with self.SessionLocal() as db:
            schema = {
                "version": 1,
                "columns": [
                    {"key": "key", "type": "string", "label": "Key", "required": True},
                    {"key": "value", "type": "number", "label": "Value", "required": True},
                ],
            }
            db.add(
                ProjectTable(
                    id="t2",
                    project_id="p1",
                    table_key="tbl_money_num",
                    name="MoneyNum",
                    schema_version=1,
                    schema_json=_compact_json_dumps(schema),
                )
            )
            db.add(
                ProjectTableRow(
                    id="r2",
                    project_id="p1",
                    table_id="t2",
                    row_index=0,
                    data_json=_compact_json_dumps({"key": "gold", "value": 50}),
                )
            )
            db.commit()

        with self.SessionLocal() as db:
            payload = TableUpdateV1Request(
                schema_version="table_update_v1",
                idempotency_key="idem-22345678",
                title="Update gold numeric",
                ops=[
                    {
                        "op": "upsert",
                        "table_id": "t2",
                        "row_id": None,
                        "data": {"key": "gold", "value": 100},
                    }
                ],
            )
            out = propose_project_table_change_set(
                db=db,
                request_id="rid-test",
                actor_user_id="u1",
                project_id="p1",
                payload=payload,
            )

            self.assertEqual(len(out.get("items") or []), 1)
            item = out["items"][0]
            self.assertEqual(item.get("target_table"), "project_table_rows")
            self.assertEqual(item.get("target_id"), "r2")

            after = json.loads(item.get("after_json") or "{}")
            self.assertEqual(after.get("data", {}).get("key"), "gold")
            self.assertEqual(after.get("data", {}).get("value"), 100)
