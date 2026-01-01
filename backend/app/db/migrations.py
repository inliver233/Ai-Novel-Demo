from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.core.logging import log_event
from app.db.session import engine as app_engine

logger = logging.getLogger("ainovel")

INIT_REVISION = "0f24b611cf21"


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_config(*, database_url: str) -> Config:
    base_dir = _backend_dir()
    cfg = Config(str(base_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(base_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _inspect_tables(engine: Engine) -> tuple[set[str], set[str]]:
    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        project_cols: set[str] = set()
        if "projects" in tables:
            project_cols = {c["name"] for c in inspector.get_columns("projects")}
        return tables, project_cols


def ensure_db_schema(*, engine: Engine = app_engine) -> None:
    """
    Ensure the DB is usable for the current codebase.

    - If DB is empty/missing: creates all tables via `alembic upgrade head`.
    - If DB is older: upgrades to head.
    - If DB is a legacy SQLite without alembic_version: attempts a safe stamp then upgrades.
    """
    database_url = settings.database_url
    cfg = _alembic_config(database_url=database_url)

    tables, project_cols = _inspect_tables(engine)

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

