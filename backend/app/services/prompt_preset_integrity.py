from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.prompt_preset_canary import PromptPresetCanaryResult, run_prompt_preset_canaries
from app.services.prompting import render_template

_ALLOWED_ROLES = {"system", "user", "assistant"}
_ALLOWED_INJECTION_POSITIONS = {"relative", "absolute"}
_ALLOWED_BUDGET_PRIORITIES = {"must", "important", "optional", "drop_first"}
_MARKER_KEY_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
_TASK_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class PromptPresetIntegrityIssue:
    severity: str
    resource_key: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class PromptPresetIntegrityReport:
    checked_resources: tuple[str, ...]
    issues: tuple[PromptPresetIntegrityIssue, ...]
    canaries: tuple[PromptPresetCanaryResult, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues) or any(not canary.passed for canary in self.canaries)


def _default_resource_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "prompt_presets"


def _display_path(path: Path, base_dir: Path) -> str:
    for candidate in (base_dir, *base_dir.parents):
        try:
            return path.relative_to(candidate).as_posix()
        except Exception:
            continue
    return path.as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def collect_prompt_preset_integrity(
    resource_keys: list[str] | None = None,
    *,
    base_dir: Path | None = None,
    include_canaries: bool = True,
) -> PromptPresetIntegrityReport:
    effective_base_dir = Path(base_dir) if base_dir is not None else _default_resource_base_dir()
    if resource_keys is None:
        keys = sorted(path.name for path in effective_base_dir.iterdir() if path.is_dir()) if effective_base_dir.exists() else []
    else:
        keys = list(resource_keys)

    issues: list[PromptPresetIntegrityIssue] = []
    checked: list[str] = []
    for resource_key in keys:
        checked.append(resource_key)
        preset_dir = effective_base_dir / resource_key
        preset_path = preset_dir / "preset.json"
        templates_dir = preset_dir / "templates"

        if not preset_dir.exists():
            issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_dir, effective_base_dir), "resource directory missing"))
            continue
        if not preset_path.exists():
            issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), "preset.json missing"))
            continue
        if not templates_dir.exists():
            issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(templates_dir, effective_base_dir), "templates directory missing"))
            continue

        raw = _read_json(preset_path)
        if raw is None:
            issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), "preset.json invalid or not an object"))
            continue

        activation_tasks_raw = raw.get("activation_tasks")
        if not isinstance(activation_tasks_raw, list) or not activation_tasks_raw:
            issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), "activation_tasks must be a non-empty list"))
            activation_tasks: list[str] = []
        else:
            activation_tasks = []
            seen_tasks: set[str] = set()
            for task in activation_tasks_raw:
                task_norm = str(task or "").strip()
                if not task_norm or not _TASK_KEY_RE.fullmatch(task_norm):
                    issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"invalid activation task: {task!r}"))
                    continue
                if task_norm in seen_tasks:
                    issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"duplicate activation task: {task_norm}"))
                    continue
                seen_tasks.add(task_norm)
                activation_tasks.append(task_norm)

        blocks_raw = raw.get("blocks")
        if not isinstance(blocks_raw, list) or not blocks_raw:
            issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), "blocks must be a non-empty list"))
            continue

        identifiers: set[str] = set()
        referenced_templates: set[str] = set()
        for index, block in enumerate(blocks_raw):
            if not isinstance(block, dict):
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"blocks[{index}] must be an object"))
                continue
            identifier = str(block.get("identifier") or "").strip()
            if not identifier:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"blocks[{index}].identifier missing"))
                continue
            if identifier in identifiers:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"duplicate block identifier: {identifier}"))
                continue
            identifiers.add(identifier)

            role = str(block.get("role") or "").strip()
            if role not in _ALLOWED_ROLES:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: unsupported role {role!r}"))

            injection_position = str(block.get("injection_position") or "relative").strip().lower()
            if injection_position not in _ALLOWED_INJECTION_POSITIONS:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: invalid injection_position {injection_position!r}"))

            marker_key = block.get("marker_key")
            if marker_key is not None:
                marker_norm = str(marker_key).strip()
                if not marker_norm or not _MARKER_KEY_RE.fullmatch(marker_norm):
                    issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: invalid marker_key {marker_key!r}"))

            triggers_raw = block.get("triggers")
            if not isinstance(triggers_raw, list) or not triggers_raw:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: triggers must be a non-empty list"))
            else:
                seen_triggers: set[str] = set()
                for trigger in triggers_raw:
                    trigger_norm = str(trigger or "").strip()
                    if not trigger_norm or not _TASK_KEY_RE.fullmatch(trigger_norm):
                        issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: invalid trigger {trigger!r}"))
                        continue
                    if trigger_norm in seen_triggers:
                        issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: duplicate trigger {trigger_norm}"))
                        continue
                    seen_triggers.add(trigger_norm)
                    if activation_tasks and trigger_norm not in activation_tasks:
                        issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: trigger {trigger_norm} not declared in activation_tasks"))

            budget = block.get("budget")
            if budget is not None and not isinstance(budget, dict):
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: budget must be an object when present"))
            elif isinstance(budget, dict):
                priority = str(budget.get("priority") or "").strip()
                if priority and priority not in _ALLOWED_BUDGET_PRIORITIES:
                    issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: invalid budget priority {priority!r}"))

            template_rel = str(block.get("template_file") or "").strip()
            if not template_rel:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"{identifier}: template_file missing"))
                continue
            template_path = (preset_dir / template_rel).resolve()
            referenced_templates.add(Path(template_rel).as_posix())
            if not template_path.exists():
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(template_path, effective_base_dir), f"{identifier}: template file missing"))
                continue
            rendered, _missing, error = render_template(template_path.read_text(encoding="utf-8"), {}, macro_seed=f"integrity:{resource_key}:{identifier}")
            if error:
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(template_path, effective_base_dir), f"{identifier}: template render validation failed: {error}"))
            if rendered == "" and str(block.get("enabled", True)).lower() == "true" and not identifier.startswith("doc."):
                pass

        upgrade_add_identifiers = raw.get("upgrade_add_identifiers") or []
        if upgrade_add_identifiers:
            if not isinstance(upgrade_add_identifiers, list):
                issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), "upgrade_add_identifiers must be a list"))
            else:
                seen_upgrade_ids: set[str] = set()
                for identifier in upgrade_add_identifiers:
                    ident_norm = str(identifier or "").strip()
                    if not ident_norm:
                        issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), "upgrade_add_identifiers contains empty identifier"))
                        continue
                    if ident_norm in seen_upgrade_ids:
                        issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"duplicate upgrade_add_identifier: {ident_norm}"))
                        continue
                    seen_upgrade_ids.add(ident_norm)
                    if ident_norm not in identifiers:
                        issues.append(PromptPresetIntegrityIssue("error", resource_key, _display_path(preset_path, effective_base_dir), f"upgrade_add_identifier missing block definition: {ident_norm}"))

        actual_templates = {
            path.relative_to(preset_dir).as_posix()
            for path in templates_dir.rglob("*.md")
            if path.is_file()
        }
        orphan_templates = sorted(actual_templates - referenced_templates)
        for orphan in orphan_templates:
            issues.append(PromptPresetIntegrityIssue("error", resource_key, orphan, "template file is not referenced by preset.json"))

    canaries = run_prompt_preset_canaries(keys, base_dir=effective_base_dir) if include_canaries else ()
    return PromptPresetIntegrityReport(
        checked_resources=tuple(checked),
        issues=tuple(issues),
        canaries=tuple(canaries),
    )
