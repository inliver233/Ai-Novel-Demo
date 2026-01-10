from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from alembic import command

from app.db import migrations


class TestMigrationsIdempotentUserPasswords(unittest.TestCase):
    def test_upgrade_head_when_user_passwords_and_is_admin_already_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "partial.db"
            database_url = f"sqlite:///{db_path.as_posix()}"
            cfg = migrations._alembic_config(database_url=database_url)

            # Create a DB schema up to the migration BEFORE user_passwords/is_admin.
            prev = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = database_url
            try:
                command.upgrade(cfg, "ca30c45d18e1")
            finally:
                if prev is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = prev

            # Simulate a prior partial/failed run:
            # - SQLite DDL isn't transactional; a failure after creating table/column but before stamping
            #   would leave DB in this state and the next upgrade would crash with "already exists".
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.execute(
                    """
                    CREATE TABLE user_passwords (
                        user_id VARCHAR(64) NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        password_updated_at DATETIME NOT NULL,
                        disabled_at DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (user_id),
                        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
                conn.commit()
            finally:
                conn.close()

            # Now upgrade should be able to continue to head without crashing.
            prev = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = database_url
            try:
                command.upgrade(cfg, "head")
            finally:
                if prev is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = prev

            # Basic sanity: users.is_admin exists.
            conn = sqlite3.connect(str(db_path))
            try:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
                self.assertIn("is_admin", cols)
            finally:
                conn.close()
