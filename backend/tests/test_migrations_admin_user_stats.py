from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from alembic import command

from app.db import migrations


class TestMigrationsAdminUserStats(unittest.TestCase):
    def test_upgrade_to_head_preserves_data_and_backfills_usage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "upgrade_stats.db"
            database_url = f"sqlite:///{db_path.as_posix()}"
            cfg = migrations._alembic_config(database_url=database_url)

            prev = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = database_url
            try:
                command.upgrade(cfg, "a4f9e5c7d2b1")
            finally:
                if prev is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = prev

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.execute(
                    """
                    INSERT INTO users (id, email, password_hash, display_name, is_admin, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("u1", None, None, "User 1", 0, "2026-03-05T00:00:00+00:00", "2026-03-05T00:00:00+00:00"),
                )
                conn.execute(
                    """
                    INSERT INTO projects (id, owner_user_id, active_outline_id, llm_profile_id, name, genre, logline, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "p1",
                        "u1",
                        None,
                        None,
                        "Project 1",
                        None,
                        None,
                        "2026-03-05T00:00:00+00:00",
                        "2026-03-05T00:00:00+00:00",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO generation_runs (
                        id, project_id, actor_user_id, chapter_id, type, provider, model, request_id,
                        prompt_system, prompt_user, prompt_render_log_json, params_json, output_text, error_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "gr1",
                        "p1",
                        "u1",
                        None,
                        "chapter_stream",
                        "mock",
                        "mock-model",
                        "rid-1",
                        "",
                        "",
                        None,
                        "{}",
                        "abc",
                        None,
                        "2026-03-05T01:00:00+00:00",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO generation_runs (
                        id, project_id, actor_user_id, chapter_id, type, provider, model, request_id,
                        prompt_system, prompt_user, prompt_render_log_json, params_json, output_text, error_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "gr2",
                        "p1",
                        "u1",
                        None,
                        "chapter_stream",
                        "mock",
                        "mock-model",
                        "rid-2",
                        "",
                        "",
                        None,
                        "{}",
                        "abcd",
                        '{"code":"X"}',
                        "2026-03-05T02:00:00+00:00",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            prev = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = database_url
            try:
                command.upgrade(cfg, "head")
                # Re-run to verify idempotent upgrade behavior.
                command.upgrade(cfg, "head")
            finally:
                if prev is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = prev

            conn = sqlite3.connect(str(db_path))
            try:
                users_count = int(conn.execute("SELECT COUNT(1) FROM users").fetchone()[0])
                runs_count = int(conn.execute("SELECT COUNT(1) FROM generation_runs").fetchone()[0])
                usage_row = conn.execute(
                    """
                    SELECT
                      total_generation_calls,
                      total_generation_error_calls,
                      total_generated_chars,
                      last_generation_at
                    FROM user_usage_stats
                    WHERE user_id = ?
                    """,
                    ("u1",),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(users_count, 1)
            self.assertEqual(runs_count, 2)
            self.assertIsNotNone(usage_row)
            assert usage_row is not None
            self.assertEqual(int(usage_row[0]), 2)
            self.assertEqual(int(usage_row[1]), 1)
            self.assertEqual(int(usage_row[2]), 7)
            self.assertTrue(str(usage_row[3] or "").startswith("2026-03-05T02:00:00"))


if __name__ == "__main__":
    unittest.main()
