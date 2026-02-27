#!/bin/sh
set -eu

export PYTHONUNBUFFERED=1

if [ "${WAIT_FOR_DB:-1}" = "1" ]; then
  python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

database_url = (os.environ.get("DATABASE_URL") or "").strip()
if not database_url:
    raise SystemExit("DATABASE_URL is required")

timeout_s = int((os.environ.get("DB_WAIT_TIMEOUT") or "60").strip() or "60")
deadline = time.time() + timeout_s

last_error = None
while time.time() < deadline:
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("DB is ready", flush=True)
        last_error = None
        break
    except Exception as exc:
        last_error = exc
        print(f"Waiting for DB... {exc}", flush=True)
        time.sleep(1)

if last_error is not None:
    raise last_error
PY
fi

python - <<'PY'
from app.db.migrations import ensure_db_schema

ensure_db_schema()
PY

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-1}"

case "$WORKERS" in
  ''|*[!0-9]*)
    WORKERS=1
    ;;
esac

case "${DATABASE_URL:-}" in
  sqlite*)
    if [ "${WORKERS:-1}" -gt 1 ] 2>/dev/null; then
      echo "SQLite 模式仅支持单 worker；已强制 WEB_CONCURRENCY=1" >&2
    fi
    WORKERS=1
    ;;
esac

exec uvicorn app.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
