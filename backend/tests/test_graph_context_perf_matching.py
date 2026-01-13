from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.project import Project
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryRelation
from app.models.user import User
from app.services.graph_context_service import query_graph_context


class TestGraphContextPerfMatching(unittest.TestCase):
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

        self.noise_count = 4000

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))

            # Add a lot of non-matching entities to simulate a large project.
            db.bulk_save_objects(
                [
                    MemoryEntity(
                        id=f"n{i}",
                        project_id="p1",
                        entity_type="generic",
                        name=f"Entity{i:04d}",
                        summary_md=None,
                        attributes_json=None,
                    )
                    for i in range(self.noise_count)
                ]
            )

            # Two real targets: one matches by name; one matches by alias only.
            db.add(MemoryEntity(id="e_alice", project_id="p1", entity_type="character", name="Alice", summary_md=None, attributes_json=None))
            db.add(
                MemoryEntity(
                    id="e_robert",
                    project_id="p1",
                    entity_type="character",
                    name="Robert",
                    summary_md=None,
                    attributes_json=json.dumps({"aliases": ["Bob"]}, ensure_ascii=False),
                )
            )
            db.commit()

    def test_matching_uses_small_candidate_set(self) -> None:
        with self.SessionLocal() as db:
            result = query_graph_context(
                db=db,
                project_id="p1",
                query_text="Bob met Alice in town.",
                hop=0,
                max_nodes=40,
                max_edges=0,
                enabled=True,
            )

        logs = list(result.get("logs") or [])
        self.assertTrue(logs, "expected logs to be present for enabled queries")
        match_meta = (logs[0] or {}).get("match_candidates") or {}

        total_entities = int(self.noise_count) + 2
        loaded = int(match_meta.get("loaded") or 0)
        name_loaded = int(match_meta.get("name_loaded") or 0)
        alias_loaded = int(match_meta.get("alias_loaded") or 0)
        self.assertLess(loaded, total_entities)
        self.assertLessEqual(loaded, 10, f"expected candidate load to stay small; got loaded={loaded}")
        self.assertEqual(name_loaded, 1)
        self.assertEqual(alias_loaded, 1)
        self.assertFalse(bool(match_meta.get("alias_truncated")))

        matched = result.get("matched") or {}
        self.assertEqual(matched.get("entity_ids"), ["e_robert", "e_alice"])
        self.assertEqual(matched.get("entity_names"), ["Robert", "Alice"])


if __name__ == "__main__":
    unittest.main()
