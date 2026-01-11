from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Response

from app.core.config import settings
from app.db.utils import utc_now

_SESSION_COOKIE_VERSION = "v1"
_DEV_SIGNING_KEY: bytes | None = None


@dataclass(frozen=True, slots=True)
class AuthSession:
    user_id: str
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes | None:
    try:
        padded = data + ("=" * ((4 - len(data) % 4) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        return None


def _get_signing_key() -> bytes:
    if settings.auth_session_signing_key:
        return settings.auth_session_signing_key.encode("utf-8")

    if settings.secret_encryption_key:
        try:
            return base64.urlsafe_b64decode(settings.secret_encryption_key.encode("ascii"))
        except Exception:
            return settings.secret_encryption_key.encode("utf-8")

    global _DEV_SIGNING_KEY
    if _DEV_SIGNING_KEY is None:
        _DEV_SIGNING_KEY = secrets.token_bytes(32)
    return _DEV_SIGNING_KEY


def _sign(payload: bytes) -> str:
    sig = hmac.new(_get_signing_key(), payload, hashlib.sha256).digest()
    return _b64url_encode(sig)


def build_session(*, user_id: str, now: datetime | None = None) -> AuthSession:
    now_dt = now or utc_now()
    expires_at = now_dt + timedelta(seconds=settings.auth_session_ttl_seconds)
    return AuthSession(user_id=user_id, expires_at=expires_at)


def encode_session_cookie(*, user_id: str, expires_at: datetime) -> str:
    exp_ts = int(expires_at.astimezone(timezone.utc).timestamp())
    payload = json.dumps({"uid": user_id, "exp": exp_ts}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_b64 = _b64url_encode(payload)
    sig_b64 = _sign(payload)
    return f"{_SESSION_COOKIE_VERSION}.{payload_b64}.{sig_b64}"


def decode_session_cookie(value: str, *, now: datetime | None = None) -> AuthSession | None:
    if not value:
        return None

    parts = value.split(".")
    if len(parts) != 3:
        return None

    version, payload_b64, sig_b64 = parts
    if version != _SESSION_COOKIE_VERSION:
        return None

    payload = _b64url_decode(payload_b64)
    if payload is None:
        return None

    expected_sig = _sign(payload)
    if not hmac.compare_digest(expected_sig, sig_b64):
        return None

    try:
        obj = json.loads(payload.decode("utf-8"))
    except Exception:
        return None

    user_id = obj.get("uid")
    exp = obj.get("exp")
    if not isinstance(user_id, str) or not user_id:
        return None
    if not isinstance(exp, int) or exp <= 0:
        return None

    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    now_dt = now or utc_now()
    if expires_at <= now_dt:
        return None

    return AuthSession(user_id=user_id, expires_at=expires_at)


def set_session_cookies(response: Response, *, user_id: str, expires_at: datetime) -> None:
    secure = settings.app_env == "prod"
    samesite = settings.auth_cookie_samesite
    max_age = max(0, int((expires_at - utc_now()).total_seconds()))

    response.set_cookie(
        key=settings.auth_cookie_user_id_name,
        value=encode_session_cookie(user_id=user_id, expires_at=expires_at),
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key=settings.auth_cookie_expire_at_name,
        value=str(int(expires_at.astimezone(timezone.utc).timestamp())),
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=max_age,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    secure = settings.app_env == "prod"
    samesite = settings.auth_cookie_samesite

    response.delete_cookie(key=settings.auth_cookie_user_id_name, path="/", secure=secure, samesite=samesite)
    response.delete_cookie(key=settings.auth_cookie_expire_at_name, path="/", secure=secure, samesite=samesite)
