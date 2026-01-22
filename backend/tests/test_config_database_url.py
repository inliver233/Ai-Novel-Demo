from __future__ import annotations

import unittest
from pathlib import Path

from app.core.config import Settings


class TestConfigDatabaseUrl(unittest.TestCase):
    def test_sqlite_relative_path_is_backend_relative(self) -> None:
        backend_dir = Path(__file__).resolve().parents[1]
        expected = (backend_dir / "ainovel.db").resolve().as_posix()

        s = Settings(database_url="sqlite:///./ainovel.db")
        self.assertEqual(s.database_url, f"sqlite:///{expected}")

    def test_sqlite_memory_is_preserved(self) -> None:
        s = Settings(database_url="sqlite:///:memory:")
        self.assertEqual(s.database_url, "sqlite:///:memory:")

    def test_non_sqlite_url_is_preserved(self) -> None:
        s = Settings(database_url="postgresql://user:pass@localhost:5432/db")
        self.assertEqual(s.database_url, "postgresql://user:pass@localhost:5432/db")

    def test_prod_disallows_auth_dev_fallback_user_id(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            Settings(app_env="prod", secret_encryption_key="test-key", auth_dev_fallback_user_id="local-user")
        self.assertIn("AUTH_DEV_FALLBACK_USER_ID", str(ctx.exception))

    def test_prod_allows_empty_auth_dev_fallback_user_id(self) -> None:
        s = Settings(app_env="prod", secret_encryption_key="test-key", auth_dev_fallback_user_id=None)
        self.assertIsNone(s.auth_dev_fallback_user_id)
