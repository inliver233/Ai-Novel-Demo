from __future__ import annotations

import hashlib
import json
import logging
import re
import traceback
from typing import Any, Literal

from app.core.config import settings
from app.core.request_id import get_request_id
from app.db.utils import utc_now_iso


def configure_logging() -> None:
    logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
    # Avoid httpx/httpcore request logs leaking sensitive query params (e.g. Gemini uses ?key=...).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


LogLevel = Literal["debug", "info", "warning", "error"]

_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:key|api_key|apikey|token)=)([^&\s]+)")
_URL_CREDENTIALS_RE = re.compile(r"(?i)\b([a-z][a-z0-9+\-.]*://)([^\s/@]*:[^\s/@]+@)")
_KEY_TOKEN_RE = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b")
_GOOGLE_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}\b")
_BEARER_TOKEN_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
_X_LLM_API_KEY_RE = re.compile(r"(?i)(x-llm-api-key\s*[:=]\s*)[^\s\"']+")


def _mask_key_token(token: str) -> str:
    key = (token or "").strip()
    if not key:
        return ""
    last4 = key[-4:] if len(key) >= 4 else key
    dash = key.find("-")
    if 0 <= dash <= 5:
        prefix = key[: dash + 1]
    else:
        prefix = key[:2]
    return f"{prefix}****{last4}"


def _redact_secrets(text: str) -> str:
    s = text
    s = _URL_CREDENTIALS_RE.sub(lambda m: m.group(1) + "***@", s)
    s = _QUERY_SECRET_RE.sub(lambda m: m.group(1) + "****", s)
    s = _KEY_TOKEN_RE.sub(lambda m: _mask_key_token(m.group(0)), s)
    s = _GOOGLE_API_KEY_RE.sub("AIza***", s)
    s = _BEARER_TOKEN_RE.sub(lambda m: m.group(1) + "***", s)
    s = _X_LLM_API_KEY_RE.sub(lambda m: m.group(1) + "***", s)
    return s


def redact_secrets_text(text: str) -> str:
    return _redact_secrets(text)


def exception_log_fields(exc: Exception) -> dict[str, Any]:
    exc_type = type(exc).__name__
    msg = str(exc)
    if settings.app_env == "dev":
        return {
            "exception_type": exc_type,
            "exception": redact_secrets_text(msg.replace("\n", " ").strip())[:500],
            # Keep stack frames but avoid including the exception message line (which may carry secrets).
            "stack": "".join(traceback.format_tb(exc.__traceback__)),
        }

    # prod: do not log exception message/stack, only a stable fingerprint.
    fingerprint = f"{exc_type}:{msg}".encode("utf-8", errors="replace")
    exc_hash = hashlib.sha256(fingerprint).hexdigest()[:12]
    return {"exception_type": exc_type, "exception_hash": exc_hash}


def log_event(logger: logging.Logger, level: LogLevel, **fields: Any) -> None:
    payload: dict[str, Any] = {
        "ts": utc_now_iso(),
        "level": level,
        **fields,
    }
    rid = get_request_id()
    if rid and "request_id" not in payload:
        payload["request_id"] = rid
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    getattr(logger, level.lower(), logger.info)(line)
