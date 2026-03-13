from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.generation_run import GenerationRun
from app.models.project import Project
from app.models.user import User
from app.models.user_usage_stat import UserUsageStat
from app.services.run_store import write_generation_run
from app.services.user_usage_service import bump_user_generation_usage as real_bump_user_generation_usage


class TestRunStoreRetry(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        User.__table__.create(engine)
        Project.__table__.create(engine)
        GenerationRun.__table__.create(engine)
        UserUsageStat.__table__.create(engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self._session_local_patch = patch("app.services.run_store.SessionLocal", self.SessionLocal)
        self._session_local_patch.start()
        self.addCleanup(self._session_local_patch.stop)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1", is_admin=False))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_write_generation_run_retries_user_usage_insert_race(self) -> None:
        attempts = {"count": 0}

        def flaky_bump(db, *, user_id: str, generated_chars: int, had_error: bool) -> None:  # type: ignore[no-untyped-def]
            if attempts["count"] == 0:
                attempts["count"] += 1
                raise IntegrityError(
                    "INSERT INTO user_usage_stats",
                    {},
                    Exception("UNIQUE constraint failed: user_usage_stats.user_id"),
                )
            real_bump_user_generation_usage(
                db,
                user_id=user_id,
                generated_chars=generated_chars,
                had_error=had_error,
            )

        with patch("app.services.run_store.bump_user_generation_usage", side_effect=flaky_bump):
            run_id = write_generation_run(
                request_id="rid-test",
                actor_user_id="u1",
                project_id="p1",
                chapter_id=None,
                run_type="chapter_generate",
                provider="openai_compatible",
                model="gpt-4o-mini",
                prompt_system="system",
                prompt_user="user",
                prompt_render_log_json=None,
                params_json="{}",
                output_text="hello",
                error_json=None,
            )

        with self.SessionLocal() as db:
            run = db.get(GenerationRun, run_id)
            stats = db.get(UserUsageStat, "u1")

        self.assertIsNotNone(run)
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(int(stats.total_generation_calls), 1)
        self.assertEqual(int(stats.total_generation_error_calls), 0)
        self.assertEqual(int(stats.total_generated_chars), 5)


if __name__ == "__main__":
    unittest.main()
