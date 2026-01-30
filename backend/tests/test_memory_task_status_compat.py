from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.memory_task import MemoryTask
from app.models.project import Project
from app.models.structured_memory import MemoryChangeSet
from app.models.user import User
from app.services.memory_update_service import list_memory_tasks


class TestMemoryTaskStatusCompat(unittest.TestCase):
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
                MemoryChangeSet.__table__,
                MemoryTask.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="p1", genre=None, logline=None))
            db.add(
                MemoryChangeSet(
                    id="cs1",
                    project_id="p1",
                    actor_user_id="u1",
                    generation_run_id=None,
                    request_id="rid-1",
                    idempotency_key="k1",
                    title="t",
                    summary_md=None,
                    status="proposed",
                )
            )
            db.add(
                MemoryTask(
                    id="t_succeeded",
                    project_id="p1",
                    change_set_id="cs1",
                    actor_user_id="u1",
                    kind="k_succeeded",
                    status="succeeded",
                )
            )
            db.add(
                MemoryTask(
                    id="t_done_legacy",
                    project_id="p1",
                    change_set_id="cs1",
                    actor_user_id="u1",
                    kind="k_done",
                    status="done",
                )
            )
            db.add(
                MemoryTask(
                    id="t_queued",
                    project_id="p1",
                    change_set_id="cs1",
                    actor_user_id="u1",
                    kind="k_queued",
                    status="queued",
                )
            )
            db.commit()

    def test_list_memory_tasks_done_includes_done_and_succeeded(self) -> None:
        with self.SessionLocal() as db:
            out = list_memory_tasks(db=db, project_id="p1", status="done", before=None, limit=50)
        items = out.get("items") or []
        ids = {it.get("id") for it in items}
        self.assertIn("t_succeeded", ids)
        self.assertIn("t_done_legacy", ids)
        for it in items:
            if it.get("id") in {"t_succeeded", "t_done_legacy"}:
                self.assertEqual(it.get("status"), "done")

    def test_list_memory_tasks_succeeded_alias_behaves_like_done(self) -> None:
        with self.SessionLocal() as db:
            out = list_memory_tasks(db=db, project_id="p1", status="succeeded", before=None, limit=50)
        items = out.get("items") or []
        ids = {it.get("id") for it in items}
        self.assertIn("t_succeeded", ids)
        self.assertIn("t_done_legacy", ids)

    def test_list_memory_tasks_queued_filters_exact(self) -> None:
        with self.SessionLocal() as db:
            out = list_memory_tasks(db=db, project_id="p1", status="queued", before=None, limit=50)
        items = out.get("items") or []
        self.assertEqual([it.get("id") for it in items], ["t_queued"])

