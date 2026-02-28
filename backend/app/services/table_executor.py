from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import AppError


TableUpdateSchemaVersion = Literal["table_update_v1"]
TableRowOpType = Literal["upsert", "delete"]

MAX_OPS_V1 = 50

_COLUMN_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_ALLOWED_TYPES = {"string", "number", "boolean", "md", "json"}


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


def normalize_schema(schema: object) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise AppError.validation(message="schema 必须是 JSON object")

    version = schema.get("version", 1)
    try:
        version_int = int(version)
    except Exception:
        raise AppError.validation(message="schema.version 必须是整数") from None
    if version_int < 1:
        raise AppError.validation(message="schema.version 必须 >= 1")

    columns_raw = schema.get("columns") if "columns" in schema else []
    if columns_raw is None:
        columns_raw = []
    if not isinstance(columns_raw, list):
        raise AppError.validation(message="schema.columns 必须是数组")

    seen: set[str] = set()
    columns: list[dict[str, Any]] = []
    for idx, c in enumerate(columns_raw):
        if not isinstance(c, dict):
            raise AppError.validation(message="schema.columns[*] 必须是 object", details={"column_index": idx})
        key = str(c.get("key") or "").strip()
        if not key:
            raise AppError.validation(message="schema.columns[*].key 不能为空", details={"column_index": idx})
        if not _COLUMN_KEY_RE.match(key):
            raise AppError.validation(
                message="schema.columns[*].key 仅允许字母数字与下划线，且长度<=64",
                details={"column_index": idx, "column_key": key},
            )
        if key in seen:
            raise AppError.validation(message="schema.columns[*].key 不能重复", details={"column_key": key})
        seen.add(key)

        col_type = str(c.get("type") or "string").strip().lower() or "string"
        if col_type not in _ALLOWED_TYPES:
            raise AppError.validation(message="schema.columns[*].type 不支持", details={"column_key": key, "type": col_type})

        label = c.get("label")
        label_str = str(label).strip() if label is not None else None
        required = bool(c.get("required")) if "required" in c else False
        columns.append({"key": key, "type": col_type, "label": label_str, "required": required})

    return {"version": version_int, "columns": columns}


def is_key_value_schema(schema: object) -> bool:
    """
    Returns True when schema looks like a Key/Value table:
    - columns: ["key"(required string), "value"(any type)]
    """
    if not isinstance(schema, dict):
        return False
    cols = schema.get("columns") if isinstance(schema.get("columns"), list) else []
    if len(cols) != 2:
        return False
    keys: list[str] = []
    key_required = False
    key_type: str | None = None
    for c in cols:
        if not isinstance(c, dict):
            return False
        k = str(c.get("key") or "").strip()
        if not k:
            return False
        keys.append(k)
        if k == "key":
            key_required = bool(c.get("required"))
            key_type = str(c.get("type") or "string").strip().lower() or "string"
    keys.sort()
    return keys == ["key", "value"] and key_required and (key_type in (None, "string"))


def validate_row_data(*, schema: dict[str, Any], data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AppError.validation(message="data 必须是 JSON object")

    cols = schema.get("columns") if isinstance(schema.get("columns"), list) else []
    col_by_key = {str(c.get("key")): c for c in cols if isinstance(c, dict) and str(c.get("key") or "").strip()}

    out: dict[str, Any] = {}
    for k, v in data.items():
        key = str(k or "").strip()
        if not key:
            raise AppError.validation(message="data 字段名不能为空")
        col = col_by_key.get(key)
        if col is None:
            raise AppError.validation(message="data 包含未知字段", details={"field": key})
        col_type = str(col.get("type") or "string")

        if v is None:
            out[key] = None
            continue

        if col_type in {"string", "md"}:
            if not isinstance(v, str):
                raise AppError.validation(message="字段类型不匹配（应为 string）", details={"field": key})
            out[key] = v
            continue
        if col_type == "number":
            if not isinstance(v, (int, float)):
                raise AppError.validation(message="字段类型不匹配（应为 number）", details={"field": key})
            num = float(v)
            if not (num == num and num not in (float("inf"), float("-inf"))):
                raise AppError.validation(message="字段类型不匹配（number 非法）", details={"field": key})
            out[key] = v
            continue
        if col_type == "boolean":
            if not isinstance(v, bool):
                raise AppError.validation(message="字段类型不匹配（应为 boolean）", details={"field": key})
            out[key] = v
            continue
        if col_type == "json":
            try:
                _compact_json_dumps(v)
            except Exception:
                raise AppError.validation(message="字段类型不匹配（应为可序列化 JSON）", details={"field": key}) from None
            out[key] = v
            continue

        raise AppError.validation(message="字段类型不支持", details={"field": key, "type": col_type})

    for key, c in col_by_key.items():
        if not bool(c.get("required")):
            continue
        if key not in out:
            raise AppError.validation(message="缺少必填字段", details={"field": key})
        val = out.get(key)
        if val is None:
            raise AppError.validation(message="必填字段不可为 null", details={"field": key})
        if isinstance(val, str) and not val.strip():
            raise AppError.validation(message="必填字段不能为空", details={"field": key})

    return out


def validate_row_data_for_table(*, schema_json: str, data: object) -> dict[str, Any]:
    schema_obj = _safe_json_loads(schema_json)
    schema_norm = normalize_schema(schema_obj) if isinstance(schema_obj, dict) else normalize_schema({})
    return validate_row_data(schema=schema_norm, data=data)


class TableRowOpV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: TableRowOpType
    table_id: str = Field(min_length=1, max_length=36)
    row_id: str | None = Field(default=None, max_length=36)
    row_index: int | None = Field(default=None, ge=0)
    data: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_op(self) -> "TableRowOpV1":
        if self.op == "delete":
            if not (self.row_id or "").strip():
                raise ValueError("row_id is required for delete")
            if self.data is not None:
                raise ValueError("data must be null for delete")
            if self.row_index is not None:
                raise ValueError("row_index must be null for delete")
            return self

        if self.data is None:
            raise ValueError("data is required for upsert")
        return self


class TableUpdateV1Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TableUpdateSchemaVersion = "table_update_v1"
    idempotency_key: str = Field(min_length=8, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    summary_md: str | None = Field(default=None, max_length=40000)
    # NOTE: allow empty ops for fail-soft/no-op AI updates (align with other auto-update contracts).
    ops: list[TableRowOpV1] = Field(default_factory=list, min_length=0, max_length=MAX_OPS_V1)
