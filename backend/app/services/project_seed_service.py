from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.utils import new_id
from app.models.project_table import ProjectTable, ProjectTableRow
from app.services.table_executor import normalize_schema, validate_row_data


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _default_numeric_kv_schema() -> dict[str, Any]:
    return {
        "version": 1,
        "columns": [
            {"key": "key", "type": "string", "label": "项目", "required": True},
            {"key": "value", "type": "number", "label": "数值", "required": True},
        ],
    }


def _default_numeric_tables() -> list[dict[str, Any]]:
    schema = _default_numeric_kv_schema()
    return [
        {
            "table_key": "tbl_money",
            "name": "金钱（Money）",
            "schema": schema,
            "rows": [
                {"key": "gold", "value": 0},
                {"key": "silver", "value": 0},
                {"key": "debt", "value": 0},
            ],
        },
        {
            "table_key": "tbl_time",
            "name": "时间（Time）",
            "schema": schema,
            "rows": [
                {"key": "day", "value": 1},
                {"key": "hour", "value": 0},
                {"key": "minute", "value": 0},
            ],
        },
        {
            "table_key": "tbl_level",
            "name": "等级/战力（Level）",
            "schema": schema,
            "rows": [
                {"key": "mc_level", "value": 1},
                {"key": "mc_power", "value": 0},
            ],
        },
        {
            "table_key": "tbl_resources",
            "name": "资源（Resources）",
            "schema": schema,
            "rows": [
                {"key": "food", "value": 0},
                {"key": "water", "value": 0},
                {"key": "ammo", "value": 0},
            ],
        },
    ]


def ensure_default_numeric_tables(db: Session, *, project_id: str) -> dict[str, Any]:
    """
    Idempotent seed:
    - Create default numeric tables when missing (money/time/level/resources).
    - Validate schema + example rows (fail-closed).
    """
    templates = _default_numeric_tables()
    created: list[str] = []
    skipped: list[str] = []

    for t in templates:
        table_key = str(t.get("table_key") or "").strip()
        if not table_key:
            continue

        exists = (
            db.execute(
                select(ProjectTable.id).where(ProjectTable.project_id == project_id, ProjectTable.table_key == table_key)
            )
            .scalars()
            .first()
            is not None
        )
        if exists:
            skipped.append(table_key)
            continue

        schema_norm = normalize_schema(t.get("schema") or {})
        schema_json = _compact_json_dumps(schema_norm)
        row = ProjectTable(
            id=new_id(),
            project_id=project_id,
            table_key=table_key,
            name=str(t.get("name") or table_key)[:255],
            auto_update_enabled=bool(t.get("auto_update_enabled", True)),
            schema_version=1,
            schema_json=schema_json,
        )
        db.add(row)
        db.flush()

        rows = t.get("rows") if isinstance(t.get("rows"), list) else []
        row_index = 0
        for data in rows:
            data_norm = validate_row_data(schema=schema_norm, data=data)
            db.add(
                ProjectTableRow(
                    id=new_id(),
                    project_id=project_id,
                    table_id=row.id,
                    row_index=row_index,
                    data_json=_compact_json_dumps(data_norm),
                )
            )
            row_index += 1

        created.append(table_key)

    if created:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        except AppError:
            db.rollback()
            raise

    return {"created": created, "skipped": skipped}
