from __future__ import annotations

import threading
from datetime import datetime

from app.core.config import settings
from app.db.datetime_compat import coerce_utc_datetime
from app.db.session import SessionLocal
from app.db.utils import utc_now
from app.models.user_activity_stat import UserActivityStat

_TOUCH_CACHE_LOCK = threading.Lock()
_TOUCH_CACHE: dict[str, float] = {}
_TOUCH_CACHE_MAX_ENTRIES = 20000
_TOUCH_CACHE_TRIM_TARGET = 15000


def _normalize_user_id(user_id: str | None) -> str:
    return str(user_id or "").strip()


def _normalize_method(method: str | None) -> str | None:
    value = str(method or "").strip().upper()
    if not value:
        return None
    return value[:16]


def _normalize_path(path: str | None) -> str | None:
    value = str(path or "").strip()
    if not value:
        return None
    return value[:255]


def _normalize_status(status_code: int | None) -> int | None:
    if status_code is None:
        return None
    try:
        value = int(status_code)
    except Exception:
        return None
    if value < 100 or value > 999:
        return None
    return value


def _touch_interval_seconds(value: int | None = None) -> int:
    if value is None:
        raw = int(getattr(settings, "auth_activity_touch_interval_seconds", 30) or 30)
    else:
        raw = int(value)
    if raw < 1:
        return 1
    if raw > 3600:
        return 3600
    return raw


def _cache_allows_touch(*, user_id: str, now_ts: float, min_interval_seconds: int) -> bool:
    with _TOUCH_CACHE_LOCK:
        last_ts = _TOUCH_CACHE.get(user_id)
        if last_ts is not None and (now_ts - last_ts) < float(min_interval_seconds):
            return False

        if len(_TOUCH_CACHE) >= _TOUCH_CACHE_MAX_ENTRIES:
            # Keep memory bounded for long-running workers.
            oldest = sorted(_TOUCH_CACHE.items(), key=lambda item: item[1])[: max(0, len(_TOUCH_CACHE) - _TOUCH_CACHE_TRIM_TARGET)]
            for key, _ in oldest:
                _TOUCH_CACHE.pop(key, None)

        _TOUCH_CACHE[user_id] = now_ts
    return True


def touch_user_activity(
    *,
    user_id: str | None,
    request_id: str | None,
    path: str | None,
    method: str | None,
    status_code: int | None,
    now: datetime | None = None,
    min_interval_seconds: int | None = None,
) -> None:
    uid = _normalize_user_id(user_id)
    if not uid:
        return

    touch_interval = _touch_interval_seconds(min_interval_seconds)
    now_dt = coerce_utc_datetime(now) if now is not None else utc_now()
    if now_dt is None:
        now_dt = utc_now()
    now_ts = now_dt.timestamp()
    if not _cache_allows_touch(user_id=uid, now_ts=now_ts, min_interval_seconds=touch_interval):
        return

    request_id_norm = str(request_id or "").strip()[:64] or None
    method_norm = _normalize_method(method)
    path_norm = _normalize_path(path)
    status_norm = _normalize_status(status_code)

    with SessionLocal() as db:
        row = db.get(UserActivityStat, uid)
        if row is None:
            db.add(
                UserActivityStat(
                    user_id=uid,
                    last_seen_at=now_dt,
                    last_seen_request_id=request_id_norm,
                    last_seen_path=path_norm,
                    last_seen_method=method_norm,
                    last_seen_status=status_norm,
                )
            )
            db.commit()
            return

        last_seen_at = coerce_utc_datetime(getattr(row, "last_seen_at", None))
        if last_seen_at is not None and (now_dt - last_seen_at).total_seconds() < float(touch_interval):
            return

        row.last_seen_at = now_dt
        row.last_seen_request_id = request_id_norm
        row.last_seen_path = path_norm
        row.last_seen_method = method_norm
        row.last_seen_status = status_norm
        db.commit()
