from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings


def _sqlite_path_from_database_url(database_url: str) -> Path:
    raw = (database_url or "").strip()
    if not raw.startswith("sqlite"):
        raise SystemExit(f"Only sqlite DATABASE_URL is supported, got: {raw!r}")
    if raw in ("sqlite:///:memory:", "sqlite://"):
        raise SystemExit("In-memory sqlite is not supported for inspection.")

    prefix = "sqlite:///"
    if not raw.startswith(prefix):
        raise SystemExit(f"Unsupported sqlite DATABASE_URL form: {raw!r}")

    db = raw[len(prefix) :]
    if not db:
        raise SystemExit(f"Invalid sqlite DATABASE_URL: {raw!r}")
    return Path(db)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    abs_path = path.expanduser().resolve()
    uri = f"file:{abs_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect projects in SQLite without writing.")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to print")
    args = parser.parse_args()

    db_path = _sqlite_path_from_database_url(settings.database_url)
    conn = _connect_readonly(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM projects")
        total_projects = int(cur.fetchone()[0])
        print(f"DB={db_path}")
        print(f"projects.count={total_projects}")

        cur.execute(
            """
            SELECT id, owner_user_id, name,
                   created_at, typeof(created_at),
                   updated_at, typeof(updated_at)
            FROM projects
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(0, args.limit),),
        )
        rows = cur.fetchall()
        for row in rows:
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
