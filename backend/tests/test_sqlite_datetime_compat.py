from __future__ import annotations

import unittest
from datetime import timezone
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.utils import utc_now
from app.models.user import User
from app.models.user_activity_stat import UserActivityStat
from app.services.user_activity_service import touch_user_activity


class TestSQLiteDatetimeCompat(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine, tables=[User.__table__, UserActivityStat.__table__])
        self.engine = engine
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _seed_legacy_activity_row(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into users (id, display_name, is_admin, created_at, updated_at)
                    values ('u1', 'user-1', 0, '2026-03-08 03:29:59', '2026-03-08 03:29:59')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    insert into user_activity_stats
                    (user_id, last_seen_at, last_seen_request_id, last_seen_path, last_seen_method, last_seen_status, created_at, updated_at)
                    values
                    ('u1', '2026-03-08 03:29:59', 'rid-old', '/api/old', 'GET', 200, '2026-03-08 03:29:59', '2026-03-08 03:29:59')
                    """
                )
            )

    def test_loaded_sqlite_timestamps_are_normalized_to_utc(self) -> None:
        self._seed_legacy_activity_row()

        with self.SessionLocal() as db:
            user = db.get(User, "u1")
            activity = db.get(UserActivityStat, "u1")

        assert user is not None
        assert activity is not None
        self.assertEqual(user.created_at.tzinfo, timezone.utc)
        self.assertEqual(user.updated_at.tzinfo, timezone.utc)
        self.assertEqual(activity.last_seen_at.tzinfo, timezone.utc)
        self.assertEqual(activity.created_at.tzinfo, timezone.utc)
        self.assertEqual(activity.updated_at.tzinfo, timezone.utc)

    def test_touch_user_activity_updates_legacy_sqlite_row_without_typeerror(self) -> None:
        self._seed_legacy_activity_row()
        now = utc_now()

        with patch("app.services.user_activity_service.SessionLocal", self.SessionLocal):
            touch_user_activity(
                user_id="u1",
                request_id="rid-new",
                path="/api/new",
                method="POST",
                status_code=204,
                now=now,
                min_interval_seconds=1,
            )

        with self.SessionLocal() as db:
            row = db.get(UserActivityStat, "u1")

        assert row is not None
        self.assertEqual(row.last_seen_request_id, "rid-new")
        self.assertEqual(row.last_seen_path, "/api/new")
        self.assertEqual(row.last_seen_method, "POST")
        self.assertEqual(row.last_seen_status, 204)
        self.assertEqual(row.last_seen_at, now)
        self.assertEqual(row.last_seen_at.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
