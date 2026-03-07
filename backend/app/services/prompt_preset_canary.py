from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.prompting import render_template


@dataclass(frozen=True, slots=True)
class PromptPresetCanaryDefinition:
    resource_key: str
    block_identifier: str
    expected_substrings: tuple[str, ...]
    values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PromptPresetCanaryResult:
    resource_key: str
    block_identifier: str
    passed: bool
    path: str
    missing: tuple[str, ...] = ()
    missing_substrings: tuple[str, ...] = ()
    error: str | None = None


def _default_resource_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "prompt_presets"


DEFAULT_PROMPT_PRESET_CANARIES: tuple[PromptPresetCanaryDefinition, ...] = (
    PromptPresetCanaryDefinition(
        resource_key="chapter_generate_v3",
        block_identifier="sys.chapter.contract.markers",
        expected_substrings=("<<<CONTENT>>>", "<<<SUMMARY>>>"),
        values={},
    ),
    PromptPresetCanaryDefinition(
        resource_key="chapter_generate_v4",
        block_identifier="sys.chapter.contract.markers",
        expected_substrings=("<<<CONTENT>>>", "<<<SUMMARY>>>"),
        values={},
    ),
    PromptPresetCanaryDefinition(
        resource_key="outline_generate_v3",
        block_identifier="sys.outline.contract.json",
        expected_substrings=("\"outline_md\"", "\"chapters\""),
        values={"chapter_count_rule": "", "chapter_detail_rule": ""},
    ),
    PromptPresetCanaryDefinition(
        resource_key="memory_update_v1",
        block_identifier="sys.memory_update.contract.json",
        expected_substrings=("schema: memory_update_v1", "\"ops\""),
        values={},
    ),
)


def _display_path(path: Path, base_dir: Path) -> str:
    for candidate in (base_dir, *base_dir.parents):
        try:
            return path.relative_to(candidate).as_posix()
        except Exception:
            continue
    return path.as_posix()


def _load_preset_json(base_dir: Path, resource_key: str) -> tuple[dict[str, Any] | None, Path]:
    preset_path = base_dir / resource_key / "preset.json"
    if not preset_path.exists():
        return None, preset_path
    try:
        raw = json.loads(preset_path.read_text(encoding="utf-8"))
    except Exception:
        return None, preset_path
    if not isinstance(raw, dict):
        return None, preset_path
    return raw, preset_path


def run_prompt_preset_canaries(
    resource_keys: list[str] | None = None,
    *,
    base_dir: Path | None = None,
) -> tuple[PromptPresetCanaryResult, ...]:
    effective_base_dir = Path(base_dir) if base_dir is not None else _default_resource_base_dir()
    requested = set(resource_keys or [])
    results: list[PromptPresetCanaryResult] = []
    for canary in DEFAULT_PROMPT_PRESET_CANARIES:
        if requested and canary.resource_key not in requested:
            continue
        raw, preset_path = _load_preset_json(effective_base_dir, canary.resource_key)
        if raw is None:
            results.append(
                PromptPresetCanaryResult(
                    resource_key=canary.resource_key,
                    block_identifier=canary.block_identifier,
                    passed=False,
                    path=_display_path(preset_path, effective_base_dir),
                    error="preset_json_missing_or_invalid",
                )
            )
            continue
        block = next(
            (
                item
                for item in raw.get("blocks") or []
                if isinstance(item, dict) and str(item.get("identifier") or "").strip() == canary.block_identifier
            ),
            None,
        )
        if block is None:
            results.append(
                PromptPresetCanaryResult(
                    resource_key=canary.resource_key,
                    block_identifier=canary.block_identifier,
                    passed=False,
                    path=_display_path(preset_path, effective_base_dir),
                    error="block_missing",
                )
            )
            continue
        template_rel = str(block.get("template_file") or "").strip()
        template_path = (effective_base_dir / canary.resource_key / template_rel).resolve()
        if not template_rel or not template_path.exists():
            results.append(
                PromptPresetCanaryResult(
                    resource_key=canary.resource_key,
                    block_identifier=canary.block_identifier,
                    passed=False,
                    path=_display_path(template_path, effective_base_dir),
                    error="template_missing",
                )
            )
            continue
        rendered, missing, error = render_template(
            template_path.read_text(encoding="utf-8"),
            dict(canary.values),
            macro_seed=f"canary:{canary.resource_key}:{canary.block_identifier}",
        )
        missing_substrings = tuple(item for item in canary.expected_substrings if item not in rendered)
        passed = not error and not missing and not missing_substrings and "{{" not in rendered and "{%" not in rendered
        results.append(
            PromptPresetCanaryResult(
                resource_key=canary.resource_key,
                block_identifier=canary.block_identifier,
                passed=passed,
                path=_display_path(template_path, effective_base_dir),
                missing=tuple(sorted(missing)),
                missing_substrings=missing_substrings,
                error=error,
            )
        )
    return tuple(results)
