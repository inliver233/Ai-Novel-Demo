from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.project import Project
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.user import User
from app.services.project_seed_service import ensure_default_numeric_tables


class TestProjectSeedServiceNumericTables(unittest.TestCase):
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
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="P1", genre=None, logline=None))
            db.commit()

    def test_ensure_default_numeric_tables_is_idempotent(self) -> None:
        with self.SessionLocal() as db:
            out = ensure_default_numeric_tables(db, project_id="p1")
            self.assertGreaterEqual(len(out.get("created") or []), 1)

        with self.SessionLocal() as db:
            tables = (
                db.execute(select(ProjectTable).where(ProjectTable.project_id == "p1").order_by(ProjectTable.table_key.asc()))
                .scalars()
                .all()
            )
            self.assertEqual(
                [t.table_key for t in tables],
                ["tbl_level", "tbl_money", "tbl_resources", "tbl_time"],
            )

            for t in tables:
                schema = json.loads(t.schema_json or "{}")
                cols = schema.get("columns") if isinstance(schema.get("columns"), list) else []
                key_col = next((c for c in cols if isinstance(c, dict) and c.get("key") == "key"), None)
                value_col = next((c for c in cols if isinstance(c, dict) and c.get("key") == "value"), None)
                self.assertIsNotNone(key_col)
                self.assertTrue(bool(key_col.get("required")))
                self.assertIsNotNone(value_col)
                self.assertEqual(str(value_col.get("type") or ""), "number")
                self.assertTrue(bool(value_col.get("required")))

            rows = db.execute(select(ProjectTableRow).where(ProjectTableRow.project_id == "p1")).scalars().all()
            self.assertGreaterEqual(len(rows), 10)

        with self.SessionLocal() as db:
            out2 = ensure_default_numeric_tables(db, project_id="p1")
            self.assertEqual(out2.get("created") or [], [])

