from __future__ import annotations

import base64
import sys
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretCryptoError(Exception):
    pass


_PREFIX_DPAPI: Final[str] = "dpapi:"
_PREFIX_PLAIN: Final[str] = "plain:"
_PREFIX_ENC: Final[str] = "enc:"


def mask_api_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return ""

    last4 = key[-4:] if len(key) >= 4 else key
    prefix = ""

    dash = key.find("-")
    if 0 <= dash <= 5:
        prefix = key[: dash + 1]
    elif key.startswith(("sk", "rk", "pk")) and len(key) >= 2:
        prefix = key[:2]

    return f"{prefix}****{last4}"


def redact_api_keys(value: object) -> object:
    """
    Redact any `*api_key*` fields in nested dict/list objects.

    Rules:
    - Keys equal to / ending with `api_key` will be converted into `has_api_key` + `masked_api_key` (with the same prefix if present).
    - Other keys that merely *contain* `api_key`/`apikey` will be replaced by a constant marker.
    """

    def _redact(v: object) -> object:
        if isinstance(v, list):
            return [_redact(item) for item in v]
        if isinstance(v, dict):
            out: dict[str, object] = {}
            for raw_key, raw_val in v.items():
                key = str(raw_key)
                key_norm = key.lower()

                if key_norm in ("api_key", "apikey") or key_norm.endswith("api_key") or key_norm.endswith("_api_key"):
                    secret = str(raw_val or "")
                    prefix = key[: -len("api_key")] if key_norm.endswith("api_key") else ""
                    prefix = prefix.rstrip("_")
                    has_key = bool(secret.strip())
                    has_field = f"{prefix + '_' if prefix else ''}has_api_key"
                    masked_field = f"{prefix + '_' if prefix else ''}masked_api_key"
                    out[has_field] = has_key
                    out[masked_field] = mask_api_key(secret) if has_key else ""
                    continue

                if "api_key" in key_norm or "apikey" in key_norm:
                    out[key] = "[REDACTED]"
                    continue

                out[key] = _redact(raw_val)
            return out
        return v

    return _redact(value)


def encrypt_secret(plaintext: str) -> str:
    raw = (plaintext or "").encode("utf-8")
    if not raw:
        return ""
    # Production: always use a portable key-based scheme so secrets can be migrated across machines/containers.
    if settings.app_env == "prod" or settings.secret_encryption_key:
        return _PREFIX_ENC + _fernet().encrypt(raw).decode("ascii")

    # Dev: allow DPAPI on Windows as a convenience for local single-user MVP.
    if sys.platform == "win32":
        encrypted = _dpapi_encrypt(raw)
        return _PREFIX_DPAPI + base64.b64encode(encrypted).decode("ascii")

    # Dev on non-win32 must still use portable encryption (no insecure fallback).
    raise SecretCryptoError("SECRET_ENCRYPTION_KEY is required on non-win32")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""

    if ciphertext.startswith(_PREFIX_DPAPI):
        if settings.app_env == "prod":
            raise SecretCryptoError("dpapi secrets are not supported in prod; migrate to enc:")
        if sys.platform != "win32":
            raise SecretCryptoError("dpapi secret cannot be decrypted on non-win32")
        raw = base64.b64decode(ciphertext[len(_PREFIX_DPAPI) :])
        decrypted = _dpapi_decrypt(raw)
        return decrypted.decode("utf-8")

    if ciphertext.startswith(_PREFIX_ENC):
        raw = ciphertext[len(_PREFIX_ENC) :].encode("ascii")
        try:
            decrypted = _fernet().decrypt(raw)
        except InvalidToken as exc:
            raise SecretCryptoError("invalid encrypted secret") from exc
        return decrypted.decode("utf-8")

    if ciphertext.startswith(_PREFIX_PLAIN):
        if settings.app_env == "prod":
            raise SecretCryptoError("plain secrets are not supported in prod; migrate to enc:")
        raw = base64.b64decode(ciphertext[len(_PREFIX_PLAIN) :])
        return raw.decode("utf-8")

    # Backward compatibility: treat as plain text in dev only.
    if settings.app_env == "dev":
        return ciphertext
    raise SecretCryptoError("unknown secret prefix")


def _fernet() -> Fernet:
    key = (settings.secret_encryption_key or "").strip()
    if not key:
        raise SecretCryptoError("SECRET_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise SecretCryptoError("SECRET_ENCRYPTION_KEY is invalid") from exc


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL

    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL

    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    _CRYPTPROTECT_UI_FORBIDDEN: Final[int] = 0x1

    def _raise_last_win_error(message: str) -> None:
        err = ctypes.get_last_error()
        raise SecretCryptoError(f"{message} (winerror={err})")

    def _blob_from_bytes(data: bytes) -> _DATA_BLOB:
        buf = ctypes.create_string_buffer(data)
        return _DATA_BLOB(cbData=len(data), pbData=ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))

    def _dpapi_encrypt(data: bytes) -> bytes:
        in_blob = _blob_from_bytes(data)
        out_blob = _DATA_BLOB()
        ok = _crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            _raise_last_win_error("CryptProtectData failed")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            _kernel32.LocalFree(out_blob.pbData)

    def _dpapi_decrypt(data: bytes) -> bytes:
        in_blob = _blob_from_bytes(data)
        out_blob = _DATA_BLOB()
        desc = wintypes.LPWSTR()
        ok = _crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            ctypes.byref(desc),
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            _raise_last_win_error("CryptUnprotectData failed")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            _kernel32.LocalFree(out_blob.pbData)
            if desc:
                _kernel32.LocalFree(desc)

else:

    def _dpapi_encrypt(data: bytes) -> bytes:  # type: ignore[no-redef]
        raise SecretCryptoError("dpapi is only available on win32")

    def _dpapi_decrypt(data: bytes) -> bytes:  # type: ignore[no-redef]
        raise SecretCryptoError("dpapi is only available on win32")
