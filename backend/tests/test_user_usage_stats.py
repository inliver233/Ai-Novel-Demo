from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.user import User
from app.models.user_usage_stat import UserUsageStat
from app.services.user_usage_service import bump_user_generation_usage, count_generated_chars


class TestUserUsageStats(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        User.__table__.create(engine)
        UserUsageStat.__table__.create(engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1", is_admin=False))
            db.commit()

    def test_count_generated_chars_uses_raw_text_length(self) -> None:
        self.assertEqual(count_generated_chars(None), 0)
        self.assertEqual(count_generated_chars(""), 0)
        self.assertEqual(count_generated_chars(" a b \n c "), 9)
        self.assertEqual(count_generated_chars("中文 空 格"), 6)

    def test_bump_user_generation_usage_accumulates(self) -> None:
        with self.SessionLocal() as db:
            bump_user_generation_usage(
                db,
                user_id="u1",
                generated_chars=120,
                had_error=False,
            )
            bump_user_generation_usage(
                db,
                user_id="u1",
                generated_chars=0,
                had_error=True,
            )
            db.commit()

        with self.SessionLocal() as db:
            row = db.get(UserUsageStat, "u1")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row.total_generation_calls), 2)
            self.assertEqual(int(row.total_generation_error_calls), 1)
            self.assertEqual(int(row.total_generated_chars), 120)
            self.assertIsNotNone(row.last_generation_at)

    def test_bump_user_generation_usage_handles_naive_existing_timestamp(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                UserUsageStat(
                    user_id="u1",
                    total_generation_calls=1,
                    total_generation_error_calls=0,
                    total_generated_chars=10,
                    last_generation_at=datetime(2026, 1, 1, 0, 0, 0),
                )
            )
            db.commit()

        with self.SessionLocal() as db:
            bump_user_generation_usage(
                db,
                user_id="u1",
                generated_chars=5,
                had_error=False,
                generated_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
            )
            db.commit()

        with self.SessionLocal() as db:
            row = db.get(UserUsageStat, "u1")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row.total_generation_calls), 2)
            self.assertEqual(int(row.total_generated_chars), 15)
            self.assertIsNotNone(row.last_generation_at)


if __name__ == "__main__":
    unittest.main()
