from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

