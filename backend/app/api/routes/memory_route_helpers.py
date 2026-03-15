from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol

from app.db.utils import new_id


class _MemoryPackLike(Protocol):
    def model_dump(self) -> dict[str, object]: ...


def _safe_json(raw: str | None, default: object) -> object:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _parse_iso_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _build_memory_pack_payload(pack: _MemoryPackLike) -> dict[str, object]:
    return pack.model_dump()


def _normalize_memory_auto_propose_args(*, focus: str | None, idempotency_key: str | None) -> tuple[str, str]:
    focus_text = str(focus or "").strip()
    key = str(idempotency_key or "").strip() or f"memupd-auto-{new_id()[:8]}"
    return focus_text, key
