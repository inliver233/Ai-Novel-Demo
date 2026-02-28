from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.project import Project
from app.models.search_index import SearchDocument
from app.models.user import User
from app.services.search_index_service import query_project_search, upsert_search_document


class TestSearchFuzzyQuery(unittest.TestCase):
    def test_fts_fuzzy_matches_non_contiguous_terms(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)

        Base.metadata.create_all(engine, tables=[User.__table__, Project.__table__, SearchDocument.__table__])
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE VIRTUAL TABLE search_index USING fts5("
                "title,content,"
                "content='search_documents',content_rowid='id',"
                "tokenize='unicode61'"
                ")"
            )

        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="p1", genre=None, logline=None))
            db.commit()

            upsert_search_document(
                db=db,
                project_id="p1",
                source_type="chapter",
                source_id="c1",
                title="第 1 章：Start",
                content="Hello brave world",
                url_path="/projects/p1/writing?chapterId=c1",
            )
            db.commit()

            out = query_project_search(db=db, project_id="p1", q="Hello world", sources=None, limit=20, offset=0)
            items = out.get("items") or []
            self.assertTrue(items)

    def test_like_fuzzy_matches_non_contiguous_terms(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)

        Base.metadata.create_all(engine, tables=[User.__table__, Project.__table__, SearchDocument.__table__])

        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="p1", genre=None, logline=None))
            db.commit()

            upsert_search_document(
                db=db,
                project_id="p1",
                source_type="chapter",
                source_id="c1",
                title="Start",
                content="Hello brave world",
                url_path="/projects/p1/writing?chapterId=c1",
            )
            db.commit()

            out = query_project_search(db=db, project_id="p1", q="Hello world", sources=None, limit=20, offset=0)
            self.assertEqual(out.get("mode"), "like")
            items = out.get("items") or []
            self.assertTrue(items)

    def test_like_order_prefers_title_match(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)

        Base.metadata.create_all(engine, tables=[User.__table__, Project.__table__, SearchDocument.__table__])

        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="p1", genre=None, logline=None))
            db.commit()

            upsert_search_document(
                db=db,
                project_id="p1",
                source_type="chapter",
                source_id="a",
                title="Hello world",
                content="",
                url_path="/projects/p1/writing?chapterId=a",
            )
            upsert_search_document(
                db=db,
                project_id="p1",
                source_type="chapter",
                source_id="b",
                title="Something else",
                content="Hello world",
                url_path="/projects/p1/writing?chapterId=b",
            )
            db.commit()

            out = query_project_search(db=db, project_id="p1", q="Hello world", sources=None, limit=20, offset=0)
            items = out.get("items") or []
            self.assertGreaterEqual(len(items), 2)
            self.assertEqual(items[0].get("source_id"), "a")

    def test_like_query_is_postgres_compatible(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)

        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        class _Dialect:
            name = "postgresql"

        class _Bind:
            dialect = _Dialect()

        class _DummyResult:
            def __init__(self, rows: list[tuple]) -> None:
                self._rows = rows

            def all(self) -> list[tuple]:
                return self._rows

        with SessionLocal() as db:
            captured_sql: dict[str, str] = {}

            def _fake_execute(sql, params):  # type: ignore[no-untyped-def]
                captured_sql["text"] = getattr(sql, "text", str(sql))
                return _DummyResult(
                    [
                        (
                            "chapter",
                            "c1",
                            "Hello world",
                            "Hello brave world",
                            "/projects/p1/writing?chapterId=c1",
                            None,
                            0,
                            0,
                            1,
                            1,
                        )
                    ]
                )

            with patch.object(db, "get_bind", return_value=_Bind()), patch.object(db, "execute", side_effect=_fake_execute):
                out = query_project_search(db=db, project_id="p1", q="Hello world", sources=None, limit=20, offset=0)

            self.assertEqual(out.get("mode"), "like")
            self.assertIn("strpos", captured_sql.get("text") or "")
            self.assertIn("ILIKE", captured_sql.get("text") or "")
            self.assertNotIn("instr(", captured_sql.get("text") or "")
