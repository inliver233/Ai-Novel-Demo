from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.utils import utc_now
from app.models.user_usage_stat import UserUsageStat


def count_generated_chars(text: str | None) -> int:
    value = str(text or "")
    return len(value)


def bump_user_generation_usage(
    db: Session,
    *,
    user_id: str,
    generated_chars: int,
    had_error: bool,
    generated_at: datetime | None = None,
) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return

    now = generated_at if generated_at is not None else utc_now()
    row = db.get(UserUsageStat, uid)
    if row is None:
        row = UserUsageStat(
            user_id=uid,
            total_generation_calls=0,
            total_generation_error_calls=0,
            total_generated_chars=0,
            last_generation_at=None,
        )
        db.add(row)
        # Ensure a second bump in the same transaction sees this row instead of creating duplicates.
        db.flush([row])

    row.total_generation_calls = int(row.total_generation_calls or 0) + 1
    if had_error:
        row.total_generation_error_calls = int(row.total_generation_error_calls or 0) + 1
    if generated_chars > 0:
        row.total_generated_chars = int(row.total_generated_chars or 0) + int(generated_chars)

    if row.last_generation_at is None or now > row.last_generation_at:
        row.last_generation_at = now
