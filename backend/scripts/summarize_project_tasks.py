from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_dt(value: object) -> datetime | None:
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


def _ms_between(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return int((b - a).total_seconds() * 1000)


def _percentile(values: list[int], p: int) -> int | None:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    ordered = sorted(values)
    idx = int(math.ceil((p / 100) * len(ordered)) - 1)
    idx = max(0, min(len(ordered) - 1, idx))
    return ordered[idx]


def _stats(values: list[int]) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "count": int(len(values)),
        "avg": int(sum(values) / len(values)),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "max": max(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize project_tasks queue wait/runtime and failure reasons.")
    parser.add_argument("--db", default=str(Path("backend") / "ainovel.db"), help="Path to SQLite DB (default: backend/ainovel.db)")
    parser.add_argument("--json", action="store_true", help="Output compact JSON (default: pretty JSON)")
    args = parser.parse_args()

    db_path = Path(str(args.db)).expanduser()
    if not db_path.exists():
        raise SystemExit(f"db not found: {db_path}")

    now = datetime.now(timezone.utc).replace(microsecond=0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT kind,status,created_at,started_at,finished_at,error_json FROM project_tasks ORDER BY created_at ASC"
        ).fetchall()
    finally:
        conn.close()

    by_kind_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_kind_wait: dict[str, list[int]] = defaultdict(list)
    by_kind_runtime: dict[str, list[int]] = defaultdict(list)
    by_kind_queue_age: dict[str, list[int]] = defaultdict(list)
    by_kind_failures: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    by_kind_failed_missing_run_id: dict[str, int] = defaultdict(int)

    total = 0
    for r in rows:
        total += 1
        kind = str(r["kind"] or "").strip() or "unknown"
        status = str(r["status"] or "").strip() or "unknown"
        by_kind_counts[kind][status] += 1
        by_kind_counts[kind]["total"] += 1

        created_at = _parse_dt(r["created_at"])
        started_at = _parse_dt(r["started_at"])
        finished_at = _parse_dt(r["finished_at"])

        queued_wait_ms = _ms_between(created_at, started_at)
        if queued_wait_ms is not None:
            by_kind_wait[kind].append(queued_wait_ms)

        runtime_ms = _ms_between(started_at, finished_at)
        if runtime_ms is not None:
            by_kind_runtime[kind].append(runtime_ms)

        if status == "queued" and created_at is not None:
            by_kind_queue_age[kind].append(int((now - created_at).total_seconds() * 1000))

        if status == "failed":
            code = "UNKNOWN"
            reason = "unknown"
            run_id: str | None = None
            raw = r["error_json"]
            if raw:
                try:
                    err = json.loads(str(raw))
                except Exception:
                    err = None
                if isinstance(err, dict):
                    code = str(err.get("code") or err.get("error", {}).get("code") or code)
                    details = err.get("details") if isinstance(err.get("details"), dict) else {}
                    if isinstance(details, dict):
                        reason = str(details.get("reason") or reason)
                        run_id = str(details.get("run_id") or "").strip() or None
            by_kind_failures[kind][(code, reason)] += 1
            if not run_id:
                by_kind_failed_missing_run_id[kind] += 1

    kinds = sorted(by_kind_counts.keys())
    by_kind_out: list[dict[str, Any]] = []
    for kind in kinds:
        failures = [
            {"code": code, "reason": reason, "count": int(count)}
            for (code, reason), count in sorted(by_kind_failures[kind].items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        by_kind_out.append(
            {
                "kind": kind,
                "counts": dict(by_kind_counts[kind]),
                "queued_wait_ms": _stats(by_kind_wait[kind]),
                "runtime_ms": _stats(by_kind_runtime[kind]),
                "queued_age_ms": _stats(by_kind_queue_age[kind]),
                "failed_missing_run_id": int(by_kind_failed_missing_run_id.get(kind, 0)),
                "failures_top": failures[:10],
            }
        )

    out = {
        "db_path": str(db_path),
        "generated_at": _utc_now_iso(),
        "total_tasks": int(total),
        "kinds": by_kind_out,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

