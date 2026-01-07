from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(r["name"]) for r in rows]


def _table_info(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({json.dumps(table)})").fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "name": str(r["name"]),
                "type": str(r["type"] or ""),
                "notnull": int(r["notnull"] or 0),
                "dflt_value": r["dflt_value"],
                "pk": int(r["pk"] or 0),
            }
        )
    out.sort(key=lambda x: x["name"])
    return out


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA foreign_key_list({json.dumps(table)})").fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "from": str(r["from"]),
                "to": str(r["to"]),
                "table": str(r["table"]),
                "on_update": str(r["on_update"]),
                "on_delete": str(r["on_delete"]),
            }
        )
    out.sort(key=lambda x: (x["table"], x["from"], x["to"]))
    return out


def _table_sql(conn: sqlite3.Connection, table: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not row:
        return None
    sql = row["sql"]
    return str(sql) if sql is not None else None


def _extract_check_constraints(table_sql: str) -> list[str]:
    # Extract CHECK(...) expressions (best-effort) and normalize whitespace for stable diffs.
    out: list[str] = []
    lower = table_sql.lower()
    i = 0
    while True:
        idx = lower.find("check", i)
        if idx < 0:
            break

        # Find the first "(" after CHECK
        j = lower.find("(", idx)
        if j < 0:
            break

        depth = 0
        k = j
        in_single = False
        in_double = False
        while k < len(table_sql):
            ch = table_sql[k]

            if in_single:
                if ch == "'" and k + 1 < len(table_sql) and table_sql[k + 1] == "'":
                    k += 2
                    continue
                if ch == "'":
                    in_single = False
                k += 1
                continue

            if in_double:
                if ch == '"':
                    in_double = False
                k += 1
                continue

            if ch == "'":
                in_single = True
                k += 1
                continue
            if ch == '"':
                in_double = True
                k += 1
                continue

            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    expr = table_sql[j + 1 : k].strip()
                    out.append(" ".join(expr.split()))
                    i = k + 1
                    break
            k += 1
        else:
            break

    return sorted(set(out))


def _check_constraints(conn: sqlite3.Connection, table: str) -> list[str]:
    sql = _table_sql(conn, table)
    if not sql:
        return []
    return _extract_check_constraints(sql)


def _index_sql(conn: sqlite3.Connection, index_name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    if not row:
        return None
    sql = row["sql"]
    return str(sql) if sql is not None else None


def _indexes(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA index_list({json.dumps(table)})").fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        name = str(r["name"])
        cols = conn.execute(f"PRAGMA index_info({json.dumps(name)})").fetchall()
        out.append(
            {
                "name": name,
                "unique": int(r["unique"] or 0),
                "origin": str(r["origin"] or ""),
                "partial": int(r["partial"] or 0),
                "columns": [str(c["name"]) if c["name"] is not None else "<expr>" for c in cols],
                "sql": _index_sql(conn, name),
            }
        )
    out.sort(key=lambda x: x["name"])
    return out


def _triggers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "name": str(r["name"]),
                "table": str(r["tbl_name"]),
                "sql": str(r["sql"] or ""),
            }
        )
    return out


def snapshot(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    conn = _connect(db_path)
    try:
        tables = _list_tables(conn)
        tables_out: dict[str, Any] = {}
        for t in tables:
            tables_out[t] = {
                "columns": _table_info(conn, t),
                "foreign_keys": _foreign_keys(conn, t),
                "indexes": _indexes(conn, t),
                "checks": _check_constraints(conn, t),
            }
        return {"tables": tables_out, "triggers": _triggers(conn)}
    finally:
        conn.close()


@dataclass(frozen=True)
class Diff:
    ok: bool
    message: str


def _diff_json(a: Any, b: Any) -> Diff:
    a_txt = json.dumps(a, ensure_ascii=False, indent=2, sort_keys=True)
    b_txt = json.dumps(b, ensure_ascii=False, indent=2, sort_keys=True)
    if a_txt == b_txt:
        return Diff(ok=True, message="OK")
    return Diff(ok=False, message=f"Schema changed.\n\n--- baseline\n+++ current\n\n{_unified_diff(a_txt, b_txt)}")


def _unified_diff(a_txt: str, b_txt: str) -> str:
    import difflib

    return "".join(
        difflib.unified_diff(
            a_txt.splitlines(keepends=True),
            b_txt.splitlines(keepends=True),
            fromfile="baseline",
            tofile="current",
        )
    )


def cmd_snapshot(args: argparse.Namespace) -> int:
    out = snapshot(Path(args.db))
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    baseline_path = Path(args.baseline)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = snapshot(Path(args.db))
    diff = _diff_json(baseline, current)
    if diff.ok:
        return 0
    sys.stderr.write(diff.message + "\n")
    return 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="SQLite schema snapshot/check (for ainovel E2E)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="Write schema snapshot to a JSON file")
    p_snap.add_argument("--db", required=True, help="Path to sqlite db file")
    p_snap.add_argument("--out", required=True, help="Output JSON path")
    p_snap.set_defaults(func=cmd_snapshot)

    p_check = sub.add_parser("check", help="Compare db schema against a baseline JSON snapshot")
    p_check.add_argument("--db", required=True, help="Path to sqlite db file")
    p_check.add_argument("--baseline", required=True, help="Baseline JSON path")
    p_check.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
