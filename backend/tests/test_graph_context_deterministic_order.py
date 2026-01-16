from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.project import Project
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryRelation
from app.models.user import User
from app.services.graph_context_service import query_graph_context


class TestGraphContextDeterministicOrder(unittest.TestCase):
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

        fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))

            db.add(MemoryEntity(id="e_bob", project_id="p1", entity_type="character", name="Bob", summary_md=None, attributes_json=None))
            db.add(
                MemoryEntity(
                    id="e_alice",
                    project_id="p1",
                    entity_type="character",
                    name="Alice",
                    summary_md=None,
                    attributes_json=None,
                )
            )
            db.add(MemoryEntity(id="e_cat", project_id="p1", entity_type="animal", name="Cat", summary_md=None, attributes_json=None))

            db.add(
                MemoryRelation(
                    id="r1",
                    project_id="p1",
                    from_entity_id="e_bob",
                    to_entity_id="e_alice",
                    relation_type="knows",
                    description_md=None,
                    attributes_json=None,
                    created_at=fixed,
                    updated_at=fixed,
                )
            )
            db.add(
                MemoryRelation(
                    id="r2",
                    project_id="p1",
                    from_entity_id="e_alice",
                    to_entity_id="e_bob",
                    relation_type="dislikes",
                    description_md=None,
                    attributes_json=None,
                    created_at=fixed,
                    updated_at=fixed,
                )
            )
            db.add(
                MemoryRelation(
                    id="r3",
                    project_id="p1",
                    from_entity_id="e_alice",
                    to_entity_id="e_cat",
                    relation_type="pets",
                    description_md=None,
                    attributes_json=None,
                    created_at=fixed,
                    updated_at=fixed,
                )
            )

            db.add(MemoryEvidence(id="ev1", project_id="p1", source_type="entity", source_id="e_alice", quote_md="A", attributes_json=None, created_at=fixed))
            db.add(MemoryEvidence(id="ev2", project_id="p1", source_type="entity", source_id="e_bob", quote_md="B", attributes_json=None, created_at=fixed))
            db.add(MemoryEvidence(id="ev3", project_id="p1", source_type="entity", source_id="e_cat", quote_md="C", attributes_json=None, created_at=fixed))
            db.add(
                MemoryEvidence(
                    id="ev4",
                    project_id="p1",
                    source_type="relation",
                    source_id="r1",
                    quote_md="R1",
                    attributes_json=None,
                    created_at=fixed,
                )
            )

            db.commit()

    def test_result_is_sorted_deterministically(self) -> None:
        with self.SessionLocal() as db:
            result = query_graph_context(
                db=db,
                project_id="p1",
                query_text="Bob met Alice.",
                hop=1,
                max_nodes=40,
                max_edges=120,
                enabled=True,
            )

        nodes = list(result.get("nodes") or [])
        edges = list(result.get("edges") or [])
        evidence = list(result.get("evidence") or [])

        self.assertEqual([n.get("name") for n in nodes], ["Alice", "Bob", "Cat"])
        self.assertEqual([e.get("relation_type") for e in edges], ["dislikes", "knows", "pets"])
        self.assertEqual([(e.get("from_name"), e.get("to_name")) for e in edges], [("Alice", "Bob"), ("Bob", "Alice"), ("Alice", "Cat")])
        self.assertEqual(
            [(ev.get("source_type"), ev.get("source_id")) for ev in evidence],
            [("entity", "e_alice"), ("entity", "e_bob"), ("entity", "e_cat"), ("relation", "r1")],
        )


if __name__ == "__main__":
    unittest.main()

