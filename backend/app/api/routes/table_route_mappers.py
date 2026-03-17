from __future__ import annotations

import json
from typing import Any

from app.models.project_table import ProjectTable, ProjectTableRow


def _safe_json_loads(value: str | None) -> Any | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _table_public(row: ProjectTable, *, include_schema: bool, row_count: int | None = None) -> dict[str, Any]:
    schema = _safe_json_loads(row.schema_json) if include_schema else None
    out: dict[str, Any] = {
        "id": row.id,
        "project_id": row.project_id,
        "table_key": row.table_key,
        "name": row.name,
        "auto_update_enabled": bool(getattr(row, "auto_update_enabled", True)),
        "schema_version": int(row.schema_version or 1),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_schema:
        out["schema"] = schema if isinstance(schema, dict) else {}
    if row_count is not None:
        out["row_count"] = int(row_count)
    return out


def _row_public(row: ProjectTableRow, *, include_data: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "project_id": row.project_id,
        "table_id": row.table_id,
        "row_index": int(row.row_index or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_data:
        data = _safe_json_loads(row.data_json)
        out["data"] = data if isinstance(data, dict) else {}
    return out
