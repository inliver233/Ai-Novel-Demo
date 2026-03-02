from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.project import Project
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryRelation
from app.models.user import User
from app.services.graph_context_service import _PROMPT_BLOCK_CHAR_LIMIT, query_graph_context


class TestGraphContextPromptBlockLimits(unittest.TestCase):
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
                MemoryEntity.__table__,
                MemoryRelation.__table__,
                MemoryEvidence.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.add(MemoryEntity(id="e1", project_id="p1", entity_type="character", name="Alice", summary_md=None, attributes_json=None))
            db.add(MemoryEntity(id="e2", project_id="p1", entity_type="character", name="Bob", summary_md=None, attributes_json=None))
            db.commit()

    def _query(self, db: Session) -> dict:
        return query_graph_context(db=db, project_id="p1", query_text="Alice", enabled=True)

    def test_prompt_block_not_truncated_when_under_limit(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                MemoryRelation(
                    id="r1",
                    project_id="p1",
                    from_entity_id="e1",
                    to_entity_id="e2",
                    relation_type="knows",
                    description_md="朋友",
                    attributes_json=None,
                )
            )
            db.commit()

            result = self._query(db)

        prompt = result.get("prompt_block") or {}
        budget_obs = result.get("budget_observability") or {}
        self.assertEqual(prompt.get("char_limit"), _PROMPT_BLOCK_CHAR_LIMIT)
        self.assertFalse(prompt.get("truncated"))
        self.assertIsInstance(prompt.get("text_md"), str)
        self.assertIn("<GraphContext>", prompt.get("text_md") or "")
        self.assertIn("</GraphContext>", prompt.get("text_md") or "")
        self.assertLessEqual(len(prompt.get("text_md") or ""), _PROMPT_BLOCK_CHAR_LIMIT)
        self.assertEqual(budget_obs.get("module"), "graph")
        self.assertEqual(int(budget_obs.get("dropped_total") or 0), 0)

    def test_prompt_block_truncates_when_over_limit(self) -> None:
        huge = "X" * (_PROMPT_BLOCK_CHAR_LIMIT * 3)
        with self.SessionLocal() as db:
            db.add(
                MemoryRelation(
                    id="r2",
                    project_id="p1",
                    from_entity_id="e1",
                    to_entity_id="e2",
                    relation_type="knows",
                    description_md=huge,
                    attributes_json=None,
                )
            )
            db.commit()

            result = self._query(db)

        prompt = result.get("prompt_block") or {}
        text_md = str(prompt.get("text_md") or "")
        budget_obs = result.get("budget_observability") or {}
        self.assertEqual(prompt.get("char_limit"), _PROMPT_BLOCK_CHAR_LIMIT)
        self.assertTrue(prompt.get("truncated"))
        self.assertIsInstance(prompt.get("original_chars"), int)
        self.assertGreater(int(prompt.get("original_chars") or 0), _PROMPT_BLOCK_CHAR_LIMIT)
        self.assertLessEqual(len(text_md), _PROMPT_BLOCK_CHAR_LIMIT)
        self.assertIn("(truncated)", text_md)
        self.assertIn("<GraphContext>", text_md)
        self.assertIn("</GraphContext>", text_md)
        dropped = result.get("dropped") or []
        self.assertTrue(any(str(item.get("reason") or "") == "prompt_char_budget" for item in dropped if isinstance(item, dict)))
        self.assertEqual(budget_obs.get("module"), "graph")
        self.assertGreaterEqual(int((budget_obs.get("dropped_by_reason") or {}).get("prompt_char_budget") or 0), 1)


if __name__ == "__main__":
    unittest.main()
