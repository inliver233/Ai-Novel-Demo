from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.errors import AppError
from app.services.prompting import render_template


@dataclass(frozen=True, slots=True)
class PromptPresetResourceBlock:
    identifier: str
    name: str
    role: str
    enabled: bool
    template: str
    marker_key: str | None
    injection_position: str
    injection_depth: int | None
    injection_order: int
    triggers: list[str]
    forbid_overrides: bool
    budget: dict[str, Any] | None
    cache: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class PromptPresetResource:
    key: str
    name: str
    category: str | None
    scope: str
    version: int
    activation_tasks: list[str]
    blocks: list[PromptPresetResourceBlock]
    upgrade_add_identifiers: list[str]


def _resource_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "prompt_presets"


def _ensure_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AppError(code="PROMPT_RESOURCE_INVALID", message="内置 Prompt 资源无效", status_code=500, details={"field": field})
    return value


def _ensure_optional_str(value: Any, *, field: str, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(code="PROMPT_RESOURCE_INVALID", message="内置 Prompt 资源无效", status_code=500, details={"field": field})
    out = value.strip()
    if not out:
        return None
    if len(out) > max_length:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"field": field, "reason": "max_length", "max_length": max_length},
        )
    return out


def _ensure_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise AppError(code="PROMPT_RESOURCE_INVALID", message="内置 Prompt 资源无效", status_code=500, details={"field": field})
    return value


def _ensure_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int):
        raise AppError(code="PROMPT_RESOURCE_INVALID", message="内置 Prompt 资源无效", status_code=500, details={"field": field})
    return value


def _ensure_str_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError(code="PROMPT_RESOURCE_INVALID", message="内置 Prompt 资源无效", status_code=500, details={"field": field})
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item)
    return out


def _read_text_file(root: Path, rel: str) -> str:
    rel_path = Path(rel)
    if rel_path.is_absolute():
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"reason": "absolute_template_path", "path": rel},
        )
    path = (root / rel_path).resolve()
    root_resolved = root.resolve()
    try:
        path.relative_to(root_resolved)
    except Exception as exc:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"reason": "template_path_escape", "path": rel},
        ) from exc
    if not path.exists():
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"reason": "template_missing", "path": rel},
        )
    return path.read_text(encoding="utf-8")


def _validate_template(*, resource_key: str, block_identifier: str, template: str) -> None:
    _, _, error = render_template(template, values={}, macro_seed="validate")
    if error:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 模板语法无效",
            status_code=500,
            details={"resource": resource_key, "block": block_identifier, "error": str(error)[:200]},
        )


@lru_cache(maxsize=64)
def load_preset_resource(resource_key: str) -> PromptPresetResource:
    base_dir = _resource_base_dir()
    preset_dir = (base_dir / resource_key).resolve()
    if not preset_dir.exists():
        raise AppError(
            code="PROMPT_RESOURCE_NOT_FOUND",
            message="内置 Prompt 资源不存在",
            status_code=500,
            details={"resource": resource_key},
        )

    preset_path = preset_dir / "preset.json"
    if not preset_path.exists():
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"resource": resource_key, "reason": "missing_preset_json"},
        )

    try:
        raw = json.loads(preset_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"resource": resource_key, "reason": "invalid_json"},
        ) from exc

    if not isinstance(raw, dict):
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"resource": resource_key, "reason": "preset_not_object"},
        )

    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"resource": resource_key, "field": "schema_version", "value": schema_version},
        )

    name = _ensure_str(raw.get("name"), field="name")
    category = _ensure_optional_str(raw.get("category"), field="category", max_length=64)
    scope = _ensure_str(raw.get("scope"), field="scope")
    version = _ensure_int(raw.get("version"), field="version")
    if version < 1:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"resource": resource_key, "field": "version", "value": version},
        )

    activation_tasks = _ensure_str_list(raw.get("activation_tasks"), field="activation_tasks")
    upgrade_add_identifiers = _ensure_str_list(raw.get("upgrade_add_identifiers"), field="upgrade_add_identifiers")

    blocks_raw = raw.get("blocks")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        raise AppError(
            code="PROMPT_RESOURCE_INVALID",
            message="内置 Prompt 资源无效",
            status_code=500,
            details={"resource": resource_key, "field": "blocks"},
        )

    blocks: list[PromptPresetResourceBlock] = []
    seen_identifiers: set[str] = set()
    for idx, b in enumerate(blocks_raw):
        if not isinstance(b, dict):
            raise AppError(
                code="PROMPT_RESOURCE_INVALID",
                message="内置 Prompt 资源无效",
                status_code=500,
                details={"resource": resource_key, "field": f"blocks[{idx}]"},
            )

        identifier = _ensure_str(b.get("identifier"), field=f"blocks[{idx}].identifier")
        if identifier in seen_identifiers:
            raise AppError(
                code="PROMPT_RESOURCE_INVALID",
                message="内置 Prompt 资源无效",
                status_code=500,
                details={"resource": resource_key, "reason": "duplicate_identifier", "identifier": identifier},
            )
        seen_identifiers.add(identifier)

        template_file = _ensure_str(b.get("template_file"), field=f"blocks[{idx}].template_file")
        template_text = _read_text_file(preset_dir, template_file)
        _validate_template(resource_key=resource_key, block_identifier=identifier, template=template_text)

        injection_position = str(b.get("injection_position") or "relative").strip().lower()
        if injection_position not in ("relative", "absolute"):
            raise AppError(
                code="PROMPT_RESOURCE_INVALID",
                message="内置 Prompt 资源无效",
                status_code=500,
                details={"resource": resource_key, "field": f"blocks[{idx}].injection_position", "value": injection_position},
            )

        injection_depth_raw = b.get("injection_depth")
        injection_depth: int | None
        if injection_depth_raw is None:
            injection_depth = None
        elif isinstance(injection_depth_raw, int) and injection_depth_raw >= 0:
            injection_depth = injection_depth_raw
        else:
            raise AppError(
                code="PROMPT_RESOURCE_INVALID",
                message="内置 Prompt 资源无效",
                status_code=500,
                details={"resource": resource_key, "field": f"blocks[{idx}].injection_depth", "value": injection_depth_raw},
            )

        budget = b.get("budget")
        if budget is not None and not isinstance(budget, dict):
            raise AppError(
                code="PROMPT_RESOURCE_INVALID",
                message="内置 Prompt 资源无效",
                status_code=500,
                details={"resource": resource_key, "field": f"blocks[{idx}].budget"},
            )
        cache = b.get("cache")
        if cache is not None and not isinstance(cache, dict):
            raise AppError(
                code="PROMPT_RESOURCE_INVALID",
                message="内置 Prompt 资源无效",
                status_code=500,
                details={"resource": resource_key, "field": f"blocks[{idx}].cache"},
            )

        blocks.append(
            PromptPresetResourceBlock(
                identifier=identifier,
                name=_ensure_str(b.get("name"), field=f"blocks[{idx}].name"),
                role=_ensure_str(b.get("role"), field=f"blocks[{idx}].role"),
                enabled=_ensure_bool(b.get("enabled"), field=f"blocks[{idx}].enabled"),
                template=template_text,
                marker_key=b.get("marker_key"),
                injection_position=injection_position,
                injection_depth=injection_depth,
                injection_order=_ensure_int(b.get("injection_order"), field=f"blocks[{idx}].injection_order"),
                triggers=_ensure_str_list(b.get("triggers"), field=f"blocks[{idx}].triggers"),
                forbid_overrides=_ensure_bool(b.get("forbid_overrides"), field=f"blocks[{idx}].forbid_overrides"),
                budget=budget,
                cache=cache,
            )
        )

    return PromptPresetResource(
        key=resource_key,
        name=name,
        category=category,
        scope=scope,
        version=version,
        activation_tasks=activation_tasks,
        blocks=blocks,
        upgrade_add_identifiers=upgrade_add_identifiers,
    )


def list_available_preset_resources() -> list[str]:
    base_dir = _resource_base_dir()
    if not base_dir.exists():
        return []
    return sorted([p.name for p in base_dir.iterdir() if p.is_dir()])
