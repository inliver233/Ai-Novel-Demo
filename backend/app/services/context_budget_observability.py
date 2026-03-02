from __future__ import annotations

from collections import defaultdict
from typing import Any


def _safe_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return int(default)


def summarize_dropped(
    *,
    dropped: list[dict[str, Any]],
    reason_explain: dict[str, str] | None = None,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts: dict[str, int] = defaultdict(int)
    sample_ids: dict[str, list[str]] = {}
    for row in dropped:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or "unknown").strip() or "unknown"
        count = max(1, _safe_int(row.get("count"), default=1))
        counts[reason] += count
        item_id = str(row.get("id") or "").strip()
        if item_id:
            bucket = sample_ids.setdefault(reason, [])
            if item_id not in bucket and len(bucket) < 5:
                bucket.append(item_id)

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    details: list[dict[str, Any]] = []
    explain = reason_explain or {}
    for reason, total in ordered:
        details.append(
            {
                "reason": reason,
                "count": int(total),
                "explain": str(explain.get(reason) or ""),
                "sample_ids": list(sample_ids.get(reason) or []),
            }
        )
    return dict(counts), details


def build_budget_observability(
    *,
    module: str,
    limits: dict[str, Any],
    dropped: list[dict[str, Any]],
    reason_explain: dict[str, str] | None = None,
) -> dict[str, Any]:
    dropped_by_reason, dropped_details = summarize_dropped(dropped=dropped, reason_explain=reason_explain)
    return {
        "module": str(module or ""),
        "limits": dict(limits or {}),
        "dropped_total": int(sum(dropped_by_reason.values())),
        "dropped_by_reason": dropped_by_reason,
        "dropped_details": dropped_details,
    }
