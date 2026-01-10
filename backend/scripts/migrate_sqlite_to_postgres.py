from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Table
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


TABLE_ORDER: list[str] = [
    "users",
    "user_passwords",
    "llm_profiles",
    "projects",
    "project_memberships",
    "project_settings",
    "llm_presets",
    "prompt_presets",
    "prompt_blocks",
    "outlines",
    "chapters",
    "characters",
    "worldbook_entries",
    "plot_analysis",
    "story_memories",
    "generation_runs",
    "batch_generation_tasks",
    "batch_generation_task_items",
]


def _backend_alembic_config(*, database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _mask_db_url(database_url: str) -> str:
    raw = (database_url or "").strip()
    try:
        url = make_url(raw)
    except Exception:
        return raw
    if url.password:
        url = url.set(password="***")
    return str(url)


def _normalize_sqlite_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise SystemExit("--source is required")
    if raw.startswith("sqlite:"):
        return raw
    path = Path(raw).expanduser().resolve()
    return f"sqlite:///{path.as_posix()}"


def _ensure_target_migrations(target_url: str) -> None:
    cfg = _backend_alembic_config(database_url=target_url)
    command.upgrade(cfg, "head")


def _pg_required_extensions(engine: Engine) -> dict[str, bool] | None:
    if engine.dialect.name != "postgresql":
        return None
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pg_trgm') ORDER BY extname"
            )
        ).fetchall()
    existing = {str(r[0]) for r in rows}
    return {"uuid-ossp": "uuid-ossp" in existing, "pg_trgm": "pg_trgm" in existing}


def _count_rows(conn: sa.Connection, table: Table) -> int:
    return int(conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def _select_samples(conn: sa.Connection, table: Table, *, limit: int) -> list[dict[str, Any]]:
    pk_cols = list(table.primary_key.columns)
    order_by = pk_cols if pk_cols else [table.c[c.name] for c in table.columns]
    rows = (
        conn.execute(sa.select(table).order_by(*order_by).limit(max(0, int(limit))))
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _sample_hash(rows: list[dict[str, Any]]) -> str:
    def _default(v: object) -> str:
        return str(v)

    txt = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=_default)
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def _missing_fk_count(conn: sa.Connection, table: Table, fk: dict[str, Any], md: sa.MetaData) -> int:
    constrained = fk.get("constrained_columns") or []
    referred_cols = fk.get("referred_columns") or []
    referred_table_name = fk.get("referred_table")
    if len(constrained) != 1 or len(referred_cols) != 1 or not referred_table_name:
        return 0

    fk_col = constrained[0]
    ref_col = referred_cols[0]
    ref_table = md.tables.get(referred_table_name)
    if ref_table is None:
        ref_table = Table(referred_table_name, md, autoload_with=conn)

    stmt = (
        sa.select(sa.func.count())
        .select_from(table.outerjoin(ref_table, table.c[fk_col] == ref_table.c[ref_col]))
        .where(table.c[fk_col].is_not(None))
        .where(ref_table.c[ref_col].is_(None))
    )
    return int(conn.execute(stmt).scalar_one())


def _copy_table(
    *,
    src_conn: sa.Connection,
    dst_engine: Engine,
    src_table: Table,
    dst_table: Table,
    chunk_size: int,
    resume: bool,
    post_insert_hook: callable[[sa.Connection], None] | None = None,
) -> int:
    inserted = 0

    if resume and dst_engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        pk_cols = [c.name for c in dst_table.primary_key.columns]
        if not pk_cols:
            raise RuntimeError(f"Table has no primary key, cannot resume safely: {dst_table.name}")
        insert_stmt = pg_insert(dst_table).on_conflict_do_nothing(index_elements=pk_cols)
    else:
        insert_stmt = dst_table.insert()

    with dst_engine.begin() as dst_conn:
        result = src_conn.execute(sa.select(src_table))
        while True:
            batch = result.mappings().fetchmany(chunk_size)
            if not batch:
                break
            rows = [dict(r) for r in batch]
            if rows:
                dst_conn.execute(insert_stmt, rows)
                inserted += len(rows)
        if post_insert_hook is not None:
            post_insert_hook(dst_conn)
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate ainovel SQLite data to Postgres (preserve IDs).")
    parser.add_argument("--source", required=True, help="SQLite DB path or sqlite:/// URL")
    parser.add_argument("--target", required=True, help="Postgres SQLAlchemy URL (e.g. postgresql://user:pass@host:5432/db)")
    parser.add_argument("--chunk-size", type=int, default=2000, help="Insert batch size per table")
    parser.add_argument("--no-migrate-schema", action="store_true", help="Skip alembic upgrade head on target")
    parser.add_argument("--resume", action="store_true", help="Idempotent mode: ON CONFLICT DO NOTHING (for retry/resume)")
    parser.add_argument("--report", default="sqlite_to_postgres.report.json", help="Write a JSON report to this path")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not write to target")
    args = parser.parse_args(argv)

    src_url = _normalize_sqlite_url(args.source)
    target_url = str((args.target or "").strip())
    if not target_url:
        raise SystemExit("--target is required")

    print(f"[source] {_mask_db_url(src_url)}")
    print(f"[target] {_mask_db_url(target_url)}")

    src_engine = sa.create_engine(src_url, connect_args={"check_same_thread": False})
    dst_engine = sa.create_engine(target_url, pool_pre_ping=True)

    if dst_engine.dialect.name != "postgresql":
        raise SystemExit(f"--target must be Postgres, got dialect={dst_engine.dialect.name!r}")

    report: dict[str, Any] = {
        "source": {"url": _mask_db_url(src_url)},
        "target": {"url": _mask_db_url(target_url)},
        "tables": {},
        "warnings": [],
    }

    if not args.no_migrate_schema:
        if args.dry_run:
            print("[plan] alembic upgrade head (target)")
        else:
            print("[step] alembic upgrade head (target)")
            _ensure_target_migrations(target_url)

    exts = _pg_required_extensions(dst_engine)
    if exts is not None:
        report["postgres_extensions"] = exts
        if not all(exts.values()):
            report["warnings"].append({"code": "PG_EXT_MISSING", "details": exts})
            print(f"[warn] postgres extensions missing: {exts}")

    src_md = sa.MetaData()
    dst_md = sa.MetaData()
    src_tables: dict[str, Table] = {}
    dst_tables: dict[str, Table] = {}

    for name in TABLE_ORDER:
        src_tables[name] = Table(name, src_md, autoload_with=src_engine)
        dst_tables[name] = Table(name, dst_md, autoload_with=dst_engine)

    # Safety check: by default require empty target so we don't duplicate real data.
    if not args.resume and not args.dry_run:
        with dst_engine.connect() as conn:
            non_empty: list[tuple[str, int]] = []
            for name in TABLE_ORDER:
                cnt = _count_rows(conn, dst_tables[name])
                if cnt:
                    non_empty.append((name, cnt))
            if non_empty:
                raise SystemExit(
                    "Target DB is not empty. Use --resume to continue a partial run.\n"
                    + "\n".join([f"- {t} count={c}" for t, c in non_empty])
                )

    # projects has a FK cycle with outlines via projects.active_outline_id (nullable).
    projects_active_outline_by_project_id: dict[str, str] = {}

    def _projects_post_insert_hook(conn: sa.Connection) -> None:
        if not projects_active_outline_by_project_id:
            return
        t_projects = dst_tables["projects"]
        for project_id, outline_id in projects_active_outline_by_project_id.items():
            conn.execute(
                sa.update(t_projects)
                .where(t_projects.c.id == project_id)
                .values(active_outline_id=outline_id)
            )

    if args.dry_run:
        print("[plan] table copy order:")
        for t in TABLE_ORDER:
            print(f"  - {t}")
        return 0

    with src_engine.connect() as src_conn:
        for name in TABLE_ORDER:
            src_table = src_tables[name]
            dst_table = dst_tables[name]

            print(f"[step] copy table={name}")

            if name == "projects":
                # Copy projects with active_outline_id cleared, then restore after outlines are copied.
                inserted = 0
                if args.resume and dst_engine.dialect.name == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert as pg_insert

                    pk_cols = [c.name for c in dst_table.primary_key.columns]
                    insert_stmt = pg_insert(dst_table).on_conflict_do_nothing(index_elements=pk_cols)
                else:
                    insert_stmt = dst_table.insert()

                with dst_engine.begin() as dst_conn:
                    result = src_conn.execute(sa.select(src_table))
                    while True:
                        batch = result.mappings().fetchmany(int(args.chunk_size))
                        if not batch:
                            break
                        rows: list[dict[str, Any]] = []
                        for r in batch:
                            row = dict(r)
                            active_outline_id = row.get("active_outline_id")
                            if active_outline_id:
                                projects_active_outline_by_project_id[str(row["id"])] = str(active_outline_id)
                            row["active_outline_id"] = None
                            rows.append(row)
                        if rows:
                            dst_conn.execute(insert_stmt, rows)
                            inserted += len(rows)
                report["tables"][name] = {"inserted": inserted}
                continue

            post_insert_hook = None
            if name == "outlines":
                post_insert_hook = _projects_post_insert_hook

            inserted = _copy_table(
                src_conn=src_conn,
                dst_engine=dst_engine,
                src_table=src_table,
                dst_table=dst_table,
                chunk_size=int(args.chunk_size),
                resume=bool(args.resume),
                post_insert_hook=post_insert_hook,
            )
            report["tables"][name] = {"inserted": inserted}

    # Verification report (counts / sample hashes / FK checks).
    sample_limit = 20
    with src_engine.connect() as sconn, dst_engine.connect() as dconn:
        for name in TABLE_ORDER:
            st = src_tables[name]
            dt = dst_tables[name]

            src_count = _count_rows(sconn, st)
            dst_count = _count_rows(dconn, dt)

            src_samples = _select_samples(sconn, st, limit=sample_limit)
            dst_samples = _select_samples(dconn, dt, limit=sample_limit)

            table_report = report["tables"].setdefault(name, {})
            table_report.update(
                {
                    "source_count": src_count,
                    "target_count": dst_count,
                    "sample_hash_source": _sample_hash(src_samples),
                    "sample_hash_target": _sample_hash(dst_samples),
                }
            )

            fk_missing_total = 0
            inspector = sa.inspect(dconn)
            for fk in inspector.get_foreign_keys(name):
                fk_missing_total += _missing_fk_count(dconn, dt, fk, dst_md)
            table_report["missing_fk_total"] = fk_missing_total

    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[ok] wrote report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
