import base64
import sys
import unittest

from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.secrets import SecretCryptoError, decrypt_secret, encrypt_secret


class TestSecretsCrypto(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = settings.app_env
        self._old_key = settings.secret_encryption_key
        self.addCleanup(self._restore_settings)

    def _restore_settings(self) -> None:
        settings.app_env = self._old_env
        settings.secret_encryption_key = self._old_key

    def test_enc_roundtrip_in_prod(self) -> None:
        settings.app_env = "prod"
        settings.secret_encryption_key = Fernet.generate_key().decode("utf-8")

        ct = encrypt_secret("hello")
        self.assertTrue(ct.startswith("enc:"))
        self.assertEqual(decrypt_secret(ct), "hello")

    def test_unknown_prefix_is_dev_only(self) -> None:
        settings.secret_encryption_key = Fernet.generate_key().decode("utf-8")

        settings.app_env = "dev"
        self.assertEqual(decrypt_secret("raw-plaintext"), "raw-plaintext")

        settings.app_env = "prod"
        with self.assertRaises(SecretCryptoError):
            decrypt_secret("raw-plaintext")

    def test_plain_prefix_is_dev_only(self) -> None:
        ct = "plain:" + base64.b64encode(b"hello").decode("ascii")

        settings.app_env = "dev"
        self.assertEqual(decrypt_secret(ct), "hello")

        settings.app_env = "prod"
        with self.assertRaises(SecretCryptoError):
            decrypt_secret(ct)

    def test_dpapi_is_dev_only(self) -> None:
        if sys.platform != "win32":
            settings.app_env = "dev"
            settings.secret_encryption_key = None
            with self.assertRaises(SecretCryptoError):
                encrypt_secret("hello")
            return

        # Encrypt/decrypt works in dev on Windows without SECRET_ENCRYPTION_KEY.
        settings.app_env = "dev"
        settings.secret_encryption_key = None
        ct = encrypt_secret("hello")
        self.assertTrue(ct.startswith("dpapi:"))
        self.assertEqual(decrypt_secret(ct), "hello")

        # dpapi ciphertext is rejected in prod (must migrate to enc:).
        settings.app_env = "prod"
        settings.secret_encryption_key = Fernet.generate_key().decode("utf-8")
        with self.assertRaises(SecretCryptoError):
            decrypt_secret(ct)


if __name__ == "__main__":
    unittest.main()
