from __future__ import annotations

import json
import logging
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
