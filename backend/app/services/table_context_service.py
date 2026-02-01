from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project_table import ProjectTable, ProjectTableRow

_TRUNCATION_MARK = "\n…(truncated)\n"


def _safe_json_loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _clip_cell(value: object, *, max_chars: int) -> str:
    s = str(value if value is not None else "").replace("\n", " ").strip()
    if max_chars > 0 and len(s) > max_chars:
        return s[: max(0, int(max_chars) - 1)].rstrip() + "…"
    return s


def _wrap_tables_text(*, inner: str, char_limit: int) -> tuple[str, bool]:
    prefix = "<TABLES>\n"
    suffix = "\n</TABLES>"
    body = (inner or "").strip()
    if not body:
        return "", False

    raw = f"{prefix}{body}{suffix}"
    if char_limit <= 0 or len(raw) <= char_limit:
        return raw, False

    budget = max(0, int(char_limit) - len(prefix) - len(suffix))
    if budget <= 0:
        return "", True

    marker = _TRUNCATION_MARK
    if budget <= len(marker):
        clipped_inner = marker[:budget]
    else:
        clipped_inner = body[: max(0, budget - len(marker))].rstrip() + marker
    clipped = f"{prefix}{clipped_inner}{suffix}"
    if len(clipped) > char_limit:
        clipped = clipped[:char_limit]
    return clipped, True


def build_tables_context_text_md(
    *,
    db: Session,
    project_id: str,
    char_limit: int,
    max_tables: int = 24,
    max_rows_per_table: int = 80,
    max_cell_chars: int = 120,
) -> dict[str, Any]:
    """
    Stable text_md format for tables injection.

    Output contract (phase 0.3):
    - enabled/disabled_reason always present
    - counts.tables / counts.rows included
    - text_md is wrapped in <TABLES> tags
    """

    tables = (
        db.execute(
            select(ProjectTable)
            .where(ProjectTable.project_id == project_id)
            .order_by(ProjectTable.table_key.asc(), ProjectTable.id.asc())
        )
        .scalars()
        .all()
    )
    if not tables:
        return {"enabled": False, "disabled_reason": "empty", "counts": {"tables": 0, "rows": 0}, "text_md": ""}

    lines: list[str] = []
    tables_used = 0
    rows_used = 0
    truncated = False

    for table in tables[: max(0, int(max_tables))]:
        tables_used += 1
        schema = _safe_json_loads_dict(str(getattr(table, "schema_json", "") or ""))
        columns_raw = schema.get("columns")
        columns: list[dict[str, Any]] = [c for c in columns_raw if isinstance(c, dict)] if isinstance(columns_raw, list) else []
        ordered_keys: list[str] = []
        for col in columns:
            key = str(col.get("key") or "").strip()
            if key:
                ordered_keys.append(key)

        lines.append(f"## {str(getattr(table, 'name', '') or '').strip() or 'Untitled'} (key:{table.table_key})")
        if columns:
            rendered_cols: list[str] = []
            for col in columns:
                key = str(col.get("key") or "").strip()
                if not key:
                    continue
                col_type = str(col.get("type") or "").strip() or "unknown"
                required = bool(col.get("required"))
                rendered_cols.append(f"{key}:{col_type}{'*' if required else ''}")
            if rendered_cols:
                lines.append("schema: " + ", ".join(rendered_cols))

        rows = (
            db.execute(
                select(ProjectTableRow)
                .where(ProjectTableRow.project_id == project_id, ProjectTableRow.table_id == table.id)
                .order_by(ProjectTableRow.row_index.asc(), ProjectTableRow.id.asc())
                .limit(max(0, int(max_rows_per_table)) + 1)
            )
            .scalars()
            .all()
        )
        if len(rows) > max(0, int(max_rows_per_table)):
            truncated = True
            rows = rows[: max(0, int(max_rows_per_table))]

        if not rows:
            lines.append("- (no rows)")
            lines.append("")
            continue

        for row in rows:
            data = _safe_json_loads_dict(str(getattr(row, "data_json", "") or ""))
            parts: list[str] = []

            used_keys: set[str] = set()
            for k in ordered_keys:
                if k not in data:
                    continue
                used_keys.add(k)
                parts.append(f"{k}={_clip_cell(data.get(k), max_chars=max_cell_chars)}")

            for k in sorted(str(x) for x in data.keys()):
                if k in used_keys:
                    continue
                parts.append(f"{k}={_clip_cell(data.get(k), max_chars=max_cell_chars)}")

            row_text = " | ".join(parts) if parts else "(empty row)"
            lines.append(f"- row {int(getattr(row, 'row_index', 0) or 0)}: {row_text}")
            rows_used += 1

        lines.append("")

    if len(tables) > max(0, int(max_tables)):
        truncated = True

    text_md, text_truncated = _wrap_tables_text(inner="\n".join(lines).strip(), char_limit=int(char_limit))
    truncated = bool(truncated or text_truncated)

    enabled = bool(text_md)
    return {
        "enabled": enabled,
        "disabled_reason": None if enabled else "empty",
        "counts": {"tables": tables_used, "rows": rows_used},
        "truncated": truncated,
        "text_md": text_md,
    }

