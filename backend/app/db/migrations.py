from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from app.core.config import settings
from app.core.logging import log_event
from app.db.session import engine as app_engine

logger = logging.getLogger("ainovel")

INIT_REVISION = "0f24b611cf21"
_DEFAULT_PG_MIGRATION_LOCK_ID = 8260228
_DEFAULT_PG_MIGRATION_LOCK_TIMEOUT_SECONDS = 60.0
_DEFAULT_PG_MIGRATION_LOCK_POLL_SECONDS = 0.2


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_config(*, database_url: str) -> Config:
    base_dir = _backend_dir()
    cfg = Config(str(base_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(base_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _inspect_tables(conn: Connection) -> tuple[set[str], set[str]]:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    project_cols: set[str] = set()
    if "projects" in tables:
        project_cols = {c["name"] for c in inspector.get_columns("projects")}
    return tables, project_cols


def _int_env(name: str, *, default: int, min_value: int, max_value: int) -> int:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _float_env(name: str, *, default: float, min_value: float, max_value: float) -> float:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except Exception:
        return default
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _acquire_pg_migration_lock(conn: Connection) -> None:
    if conn.dialect.name != "postgresql":
        return

    lock_id = _int_env(
        "DB_MIGRATION_LOCK_ID",
        default=_DEFAULT_PG_MIGRATION_LOCK_ID,
        min_value=1,
        max_value=2**31 - 1,
    )
    timeout_s = _float_env(
        "DB_MIGRATION_LOCK_TIMEOUT_SECONDS",
        default=_DEFAULT_PG_MIGRATION_LOCK_TIMEOUT_SECONDS,
        min_value=1.0,
        max_value=600.0,
    )
    poll_s = _float_env(
        "DB_MIGRATION_LOCK_POLL_SECONDS",
        default=_DEFAULT_PG_MIGRATION_LOCK_POLL_SECONDS,
        min_value=0.05,
        max_value=2.0,
    )

    deadline = time.time() + float(timeout_s)
    while True:
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id}).scalar())
        if got:
            log_event(logger, "info", event="DB_SCHEMA", action="pg_advisory_lock", lock_id=lock_id)
            return
        if time.time() >= deadline:
            log_event(logger, "error", event="DB_SCHEMA", action="pg_advisory_lock_timeout", lock_id=lock_id, timeout_s=timeout_s)
            raise RuntimeError(f"Failed to acquire Postgres migration lock within {timeout_s:.0f}s (lock_id={lock_id})")
        time.sleep(float(poll_s))


def _release_pg_migration_lock(conn: Connection) -> None:
    if conn.dialect.name != "postgresql":
        return
    lock_id = _int_env(
        "DB_MIGRATION_LOCK_ID",
        default=_DEFAULT_PG_MIGRATION_LOCK_ID,
        min_value=1,
        max_value=2**31 - 1,
    )
    try:
        conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
    except Exception:
        pass


def ensure_db_schema(*, engine: Engine = app_engine) -> None:
    """
    Ensure the DB is usable for the current codebase.

    - If DB is empty/missing: creates all tables via `alembic upgrade head`.
    - If DB is older: upgrades to head.
    - If DB is a legacy SQLite without alembic_version: attempts a safe stamp then upgrades.
    """
    database_url = settings.database_url
    cfg = _alembic_config(database_url=database_url)

    # SQLAlchemy 2.0 will implicitly open a transaction on first execute; if we don't
    # manage it explicitly, `alembic upgrade` may run inside that implicit transaction
    # and then be rolled back when the connection is closed (observed in Docker/PG).
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        _acquire_pg_migration_lock(conn)
        try:
            tables, project_cols = _inspect_tables(conn)

            if settings.is_sqlite() and tables and "alembic_version" not in tables:
                has_new_schema = (
                    "outlines" in tables
                    and "llm_profiles" in tables
                    and {"active_outline_id", "llm_profile_id"}.issubset(project_cols)
                )
                stamp_target = "head" if has_new_schema else INIT_REVISION
                if settings.app_env == "prod":
                    log_event(
                        logger,
                        "error",
                        event="DB_SCHEMA",
                        action="stamp_skipped",
                        reason="prod_env",
                        target=stamp_target,
                    )
                    raise RuntimeError(
                        "Detected a legacy SQLite database without alembic_version. "
                        "Automatic `alembic stamp` is disabled in APP_ENV=prod. "
                        "Please backup the DB and run a manual stamp/upgrade."
                    )
                log_event(logger, "warning", event="DB_SCHEMA", action="stamp", target=stamp_target)
                command.stamp(cfg, stamp_target)

            log_event(logger, "info", event="DB_SCHEMA", action="upgrade", target="head")
            command.upgrade(cfg, "head")
        finally:
            _release_pg_migration_lock(conn)
