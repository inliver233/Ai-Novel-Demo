from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import event, inspect
from sqlalchemy.sql.sqltypes import DateTime as SQLAlchemyDateTime

from app.core.config import settings
from app.db.base import Base


UTC = timezone.utc


def coerce_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_datetime_iso(value: Any) -> str | None:
    dt = coerce_utc_datetime(value)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def normalize_instance_datetime_fields(instance: object, *, attrs: Iterable[str] | None = None) -> None:
    if not settings.is_sqlite():
        return

    wanted = set(attrs) if attrs is not None else None
    state = inspect(instance)
    loaded = state.dict
    for prop in state.mapper.column_attrs:
        key = prop.key
        if wanted is not None and key not in wanted:
            continue
        if key not in loaded:
            continue
        column = prop.columns[0] if prop.columns else None
        if column is None or not isinstance(column.type, SQLAlchemyDateTime):
            continue

        current = loaded.get(key)
        normalized = coerce_utc_datetime(current)
        if normalized is None or normalized == current:
            continue
        setattr(instance, key, normalized)


@event.listens_for(Base, "load", propagate=True)
def _normalize_datetime_fields_on_load(target: object, _context) -> None:  # type: ignore[no-untyped-def]
    normalize_instance_datetime_fields(target)


@event.listens_for(Base, "refresh", propagate=True)
def _normalize_datetime_fields_on_refresh(target: object, _context, attrs) -> None:  # type: ignore[no-untyped-def]
    normalize_instance_datetime_fields(target, attrs=attrs)
