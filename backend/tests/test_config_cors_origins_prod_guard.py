from __future__ import annotations

import unittest

from app.core.config import Settings


class TestConfigCorsOriginsProdGuard(unittest.TestCase):
    def test_prod_disallows_wildcard_origin(self) -> None:
        with self.assertRaises(ValueError):
            Settings(app_env="prod", secret_encryption_key="test", auth_dev_fallback_user_id=None, cors_origins="*")

    def test_prod_disallows_null_origin(self) -> None:
        with self.assertRaises(ValueError):
            Settings(app_env="prod", secret_encryption_key="test", auth_dev_fallback_user_id=None, cors_origins="null")

    def test_prod_allows_explicit_origins(self) -> None:
        s = Settings(
            app_env="prod",
            secret_encryption_key="test",
            auth_dev_fallback_user_id=None,
            cors_origins="https://example.com,https://app.example.com",
        )
        self.assertEqual(s.cors_origins_list(), ["https://example.com", "https://app.example.com"])
