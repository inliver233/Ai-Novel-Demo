#!/bin/sh
set -eu

export PYTHONUNBUFFERED=1

if [ -z "${SECRET_ENCRYPTION_KEY:-}" ]; then
  SECRETS_DIR="${SECRETS_DIR:-/data/secrets}"
  SECRET_KEY_FILE="${SECRET_ENCRYPTION_KEY_FILE:-$SECRETS_DIR/secret_encryption_key}"
  export SECRET_KEY_FILE
  SECRET_ENCRYPTION_KEY="$(python - <<'PY'
import os
import secrets
import time
from pathlib import Path

from cryptography.fernet import Fernet

path = Path(os.environ.get("SECRET_KEY_FILE") or "/data/secrets/secret_encryption_key")
lock_path = Path(str(path) + ".lock")

wait_seconds = float(str(os.environ.get("SECRET_KEY_WAIT_SECONDS") or "10").strip() or 10)
stale_lock_seconds = float(str(os.environ.get("SECRET_KEY_LOCK_STALE_SECONDS") or "120").strip() or 120)
poll_seconds = float(str(os.environ.get("SECRET_KEY_POLL_SECONDS") or "0.2").strip() or 0.2)
deadline = time.time() + wait_seconds


def read_existing() -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

existing = read_existing()
if existing:
    print(existing)
    raise SystemExit(0)

key = Fernet.generate_key().decode("ascii")
try:
    path.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

while True:
    existing = read_existing()
    if existing:
        print(existing)
        raise SystemExit(0)

    have_lock = False
    try:
        fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        have_lock = True
    except FileExistsError:
        have_lock = False
    except Exception:
        have_lock = False

    if have_lock:
        tmp = None
        try:
            existing = read_existing()
            if existing:
                print(existing)
                raise SystemExit(0)

            tmp = Path(str(path) + f".tmp.{secrets.token_hex(8)}")
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(key)

            os.replace(str(tmp), str(path))
            tmp = None
            print(key)
            raise SystemExit(0)
        finally:
            try:
                os.unlink(str(lock_path))
            except Exception:
                pass
            if tmp is not None:
                try:
                    tmp.unlink()
                except Exception:
                    pass

    # Another process is initializing the key: wait, but protect against a stale lock.
    now = time.time()
    if now >= deadline:
        try:
            age = now - float(lock_path.stat().st_mtime)
            if age >= stale_lock_seconds:
                try:
                    lock_path.unlink()
                except Exception:
                    pass
        except Exception:
            pass
        deadline = now + wait_seconds

    time.sleep(max(0.05, poll_seconds))
PY
)"
  export SECRET_ENCRYPTION_KEY
fi

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

SHOULD_BOOTSTRAP_DB=1
if [ "$#" -gt 0 ]; then
  SHOULD_BOOTSTRAP_DB=0
fi

case "$(printf '%s' "${RUN_DB_BOOTSTRAP:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    SHOULD_BOOTSTRAP_DB=1
    ;;
  0|false|no|off)
    SHOULD_BOOTSTRAP_DB=0
    ;;
esac

if [ "$SHOULD_BOOTSTRAP_DB" -eq 1 ]; then
  python - <<'PY'
from app.core.logging import configure_logging
from app.db.migrations import ensure_db_schema

configure_logging()

ensure_db_schema()
PY

  python - <<'PY'
from app.core.errors import AppError
from app.core.logging import configure_logging, log_event
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.auth_service import ensure_admin_user

import logging

configure_logging()
logger = logging.getLogger("ainovel")

db = SessionLocal()
try:
    ensure_admin_user(db)
except AppError as exc:
    raw = (settings.auth_admin_password or "").strip()
    if settings.app_env == "dev" and exc.code == "VALIDATION_ERROR" and raw and len(raw) < 8:
        log_event(
            logger,
            "warning",
            event="AUTH_ADMIN_BOOTSTRAP",
            action="skipped",
            reason="invalid_password",
            admin_user_id=settings.auth_admin_user_id,
            password_length=len(raw),
            min_password_length=8,
            message="AUTH_ADMIN_PASSWORD 无效（长度 < 8），跳过 admin bootstrap（dev only）",
        )
    else:
        raise
finally:
    db.close()
PY

  export AINOVEL_BOOTSTRAP_DONE=1
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

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

exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
