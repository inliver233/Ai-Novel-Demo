from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import sys
import traceback
from typing import Any, Literal

from loguru import logger as loguru_logger

from app.core.config import settings
from app.core.request_id import get_request_id
from app.db.utils import utc_now_iso

LogLevel = Literal["debug", "info", "warning", "error"]

_INTERCEPT_LOGGER_NAMES = (
    "ainovel",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "fastapi",
    "httpx",
    "httpcore",
    "sqlalchemy",
    "py.warnings",
)

_SAFE_LOG_DETAIL_KEYS = frozenset(
    {
        "status_code",
        "upstream_error",
        "compat_adjustments",
        "compat_dropped_params",
        "errors",
        "attempts",
        "attempt_max",
        "provider",
        "model",
        "base_url_host",
        "timeout_seconds",
        "dropped_params",
        "finish_reason",
        "latency_ms",
    }
)

_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:key|api_key|apikey|token)=)([^&\s]+)")
_URL_CREDENTIALS_RE = re.compile(r"(?i)\b([a-z][a-z0-9+\-.]*://)([^\s/@]*:[^\s/@]+@)")
_KEY_TOKEN_RE = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b")
_GOOGLE_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}\b")
_BEARER_TOKEN_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
_X_LLM_API_KEY_RE = re.compile(r"(?i)(x-llm-api-key\s*[:=]\s*)[^\s\"']+")


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = inspect.currentframe()
        depth = 0
        while frame is not None:
            filename = frame.f_code.co_filename
            is_logging_frame = filename == logging.__file__
            is_importlib_bootstrap = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging_frame or is_importlib_bootstrap):
                break
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _logging_level_name() -> str:
    return str(settings.log_level or "INFO").upper()


def _logging_level_number() -> int:
    return getattr(logging, _logging_level_name(), logging.INFO)


def configure_logging() -> None:
    loguru_logger.remove()
    loguru_logger.add(
        sys.stderr,
        level=_logging_level_name(),
        format="{message}",
        backtrace=settings.app_env == "dev",
        diagnose=False,
        catch=True,
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [InterceptHandler()]
    root_logger.setLevel(_logging_level_number())

    for logger_name in _INTERCEPT_LOGGER_NAMES:
        current_logger = logging.getLogger(logger_name)
        current_logger.handlers.clear()
        current_logger.propagate = True

    logging.captureWarnings(True)

    # Avoid httpx/httpcore request logs leaking sensitive query params (e.g. Gemini uses ?key=...).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


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


def safe_log_details(
    details: object | None,
    *,
    extra_allowed: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(details, dict):
        return None

    allowed = set(_SAFE_LOG_DETAIL_KEYS)
    if extra_allowed:
        allowed.update(extra_allowed)

    safe: dict[str, Any] = {}
    for key, value in details.items():
        if key not in allowed:
            continue
        if key == "upstream_error" and isinstance(value, str):
            safe[key] = redact_secrets_text(value)[:500]
        else:
            safe[key] = value
    return safe or None


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
    loguru_logger.log(level.upper(), line)

