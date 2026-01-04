from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.utils import new_id
from app.llm.messages import ChatMessage, flatten_messages, normalize_role
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.services.prompt_budget import estimate_tokens, trim_text_to_tokens
from app.services.prompt_preset_resources import load_preset_resource
from app.services.prompting import render_template


LEGACY_IMPORTED_SCOPE = "legacy_imported"
DEFAULT_PLAN_PRESET_NAME = "Default plan_chapter v1"
DEFAULT_POST_EDIT_PRESET_NAME = "Default post_edit v1"
DEFAULT_OUTLINE_PRESET_NAME = "默认·大纲生成 v3（推荐）"
DEFAULT_CHAPTER_PRESET_NAME = "默认·章节生成 v3（推荐）"
DEFAULT_CHAPTER_ANALYZE_PRESET_NAME = "默认·章节分析 v1（推荐）"
DEFAULT_CHAPTER_REWRITE_PRESET_NAME = "默认·章节重写 v1（推荐）"


def parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def parse_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    if isinstance(value, dict):
        return value
    return {}


def _prompt_block_from_resource(preset_id: str, block_resource: Any) -> PromptBlock:
    triggers_json = json.dumps(list(block_resource.triggers or []), ensure_ascii=False)
    budget_json = json.dumps(block_resource.budget, ensure_ascii=False) if block_resource.budget else None
    cache_json = json.dumps(block_resource.cache, ensure_ascii=False) if block_resource.cache else None
    return PromptBlock(
        id=new_id(),
        preset_id=preset_id,
        identifier=str(block_resource.identifier),
        name=str(block_resource.name),
        role=str(block_resource.role),
        enabled=bool(block_resource.enabled),
        template=str(block_resource.template or ""),
        marker_key=block_resource.marker_key,
        injection_position=str(block_resource.injection_position),
        injection_depth=block_resource.injection_depth,
        injection_order=int(block_resource.injection_order),
        triggers_json=triggers_json,
        forbid_overrides=bool(block_resource.forbid_overrides),
        budget_json=budget_json,
        cache_json=cache_json,
    )


def _ensure_default_preset_from_resource(
    db: Session,
    *,
    project_id: str,
    resource_key: str,
    activate: bool,
) -> PromptPreset:
    resource = load_preset_resource(resource_key)

    preset = (
        db.execute(select(PromptPreset).where(PromptPreset.project_id == project_id, PromptPreset.name == resource.name))
        .scalars()
        .first()
    )

    changed = False
    if preset is not None:
        if activate and resource.activation_tasks:
            active_for = parse_json_list(preset.active_for_json)
            merged = list(dict.fromkeys([*active_for, *resource.activation_tasks]))
            if merged != active_for:
                preset.active_for_json = json.dumps(merged, ensure_ascii=False)
                changed = True

        if resource.upgrade_add_identifiers:
            blocks_by_identifier = {b.identifier: b for b in resource.blocks}
            existing_identifiers = set(
                db.execute(select(PromptBlock.identifier).where(PromptBlock.preset_id == preset.id)).scalars().all()
            )
            to_add: list[PromptBlock] = []
            for identifier in resource.upgrade_add_identifiers:
                if identifier in existing_identifiers:
                    continue
                block_res = blocks_by_identifier.get(identifier)
                if block_res is None:
                    continue
                to_add.append(_prompt_block_from_resource(preset.id, block_res))
            if to_add:
                db.add_all(to_add)
                changed = True

        if changed:
            db.commit()
            db.refresh(preset)
        return preset

    preset = PromptPreset(
        id=new_id(),
        project_id=project_id,
        name=resource.name,
        scope=resource.scope,
        version=resource.version,
        active_for_json=json.dumps(resource.activation_tasks if activate else [], ensure_ascii=False),
    )
    db.add(preset)
    db.flush()

    blocks = [_prompt_block_from_resource(preset.id, b) for b in resource.blocks]
    db.add_all(blocks)
    db.commit()
    db.refresh(preset)
    return preset


def ensure_default_plan_preset(db: Session, *, project_id: str) -> PromptPreset:
    return _ensure_default_preset_from_resource(db, project_id=project_id, resource_key="plan_chapter_v1", activate=True)


def ensure_default_post_edit_preset(db: Session, *, project_id: str) -> PromptPreset:
    return _ensure_default_preset_from_resource(db, project_id=project_id, resource_key="post_edit_v1", activate=True)


def ensure_default_outline_preset(db: Session, *, project_id: str, activate: bool = False) -> PromptPreset:
    return _ensure_default_preset_from_resource(
        db,
        project_id=project_id,
        resource_key="outline_generate_v3",
        activate=activate,
    )


def ensure_default_chapter_preset(db: Session, *, project_id: str, activate: bool = False) -> PromptPreset:
    return _ensure_default_preset_from_resource(
        db,
        project_id=project_id,
        resource_key="chapter_generate_v3",
        activate=activate,
    )


def ensure_default_chapter_analyze_preset(db: Session, *, project_id: str, activate: bool = False) -> PromptPreset:
    return _ensure_default_preset_from_resource(
        db,
        project_id=project_id,
        resource_key="chapter_analyze_v1",
        activate=activate,
    )


def ensure_default_chapter_rewrite_preset(db: Session, *, project_id: str, activate: bool = False) -> PromptPreset:
    return _ensure_default_preset_from_resource(
        db,
        project_id=project_id,
        resource_key="chapter_rewrite_v1",
        activate=activate,
    )


def get_active_preset_for_task(db: Session, *, project_id: str, task: str, allow_autocreate: bool = True) -> PromptPreset:
    presets = (
        db.execute(select(PromptPreset).where(PromptPreset.project_id == project_id).order_by(PromptPreset.updated_at.desc()))
        .scalars()
        .all()
    )

    for preset in presets:
        if (preset.scope or "") == LEGACY_IMPORTED_SCOPE:
            continue
        if task in parse_json_list(preset.active_for_json):
            return preset

    for preset in presets:
        if (preset.scope or "") != LEGACY_IMPORTED_SCOPE:
            continue
        if task in parse_json_list(preset.active_for_json):
            return preset

    if allow_autocreate:
        if task == "plan_chapter":
            return ensure_default_plan_preset(db, project_id=project_id)
        if task == "post_edit":
            return ensure_default_post_edit_preset(db, project_id=project_id)
        if task == "outline_generate":
            return ensure_default_outline_preset(db, project_id=project_id, activate=True)
        if task == "chapter_generate":
            return ensure_default_chapter_preset(db, project_id=project_id, activate=True)
        if task == "chapter_analyze":
            return ensure_default_chapter_analyze_preset(db, project_id=project_id, activate=True)
        if task == "chapter_rewrite":
            return ensure_default_chapter_rewrite_preset(db, project_id=project_id, activate=True)

    if not allow_autocreate:
        raise AppError.validation(message=f"当前项目未为 task={task} 配置可用 PromptPreset，请先在 Prompt Studio 初始化/激活")

    if presets:
        return presets[0]

    # Last resort: create a minimal preset so generation won't crash.
    preset = PromptPreset(
        id=new_id(),
        project_id=project_id,
        name=f"Auto-created ({task})",
        scope="project",
        version=1,
        active_for_json=json.dumps([task], ensure_ascii=False),
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


@dataclass(slots=True)
class RenderedBlock:
    id: str
    identifier: str
    role: str
    enabled: bool
    text: str
    missing: list[str]
    token_estimate: int


def render_preset_for_task(
    db: Session,
    *,
    project_id: str,
    task: str,
    values: dict[str, Any],
    preset_id: str | None = None,
    macro_seed: str | None = None,
    provider: str | None = None,
    prompt_budget_tokens: int | None = None,
    allow_autocreate: bool = True,
) -> tuple[str, str, list[ChatMessage], list[str], list[RenderedBlock], str, dict]:
    if preset_id is None:
        preset = get_active_preset_for_task(db, project_id=project_id, task=task, allow_autocreate=allow_autocreate)
    else:
        preset = db.get(PromptPreset, preset_id)
        if preset is None or preset.project_id != project_id:
            preset = get_active_preset_for_task(db, project_id=project_id, task=task, allow_autocreate=allow_autocreate)

    blocks = (
        db.execute(
            select(PromptBlock)
            .where(PromptBlock.preset_id == preset.id)
            .order_by(PromptBlock.injection_order.asc(), PromptBlock.created_at.asc())
        )
        .scalars()
        .all()
    )

    priority_rank: dict[str, int] = {"drop_first": 0, "optional": 1, "important": 2, "must": 3}
    default_budget_by_provider: dict[str, int] = {
        "openai": 24000,
        "openai_compatible": 24000,
        "anthropic": 12000,
        "gemini": 12000,
    }
    budget_tokens = prompt_budget_tokens
    if budget_tokens is None:
        budget_tokens = default_budget_by_provider.get(provider or "", 24000)

    all_missing: set[str] = set()
    block_states: list[dict] = []
    effective_index_by_identifier: dict[str, int] = {}

    def _try_get_marker_value(values_obj: dict[str, Any], marker_key: str) -> tuple[bool, Any]:
        if marker_key in values_obj:
            return True, values_obj.get(marker_key)
        if "." not in marker_key:
            return False, None
        cur: Any = values_obj
        for part in marker_key.split("."):
            if isinstance(cur, dict):
                if part not in cur:
                    return False, None
                cur = cur.get(part)
                continue
            if isinstance(cur, list) and part.isdigit():
                idx = int(part)
                if idx < 0 or idx >= len(cur):
                    return False, None
                cur = cur[idx]
                continue
            return False, None
        return True, cur

    for b in blocks:
        if not b.enabled:
            continue
        triggers = parse_json_list(b.triggers_json)
        if triggers and task not in triggers:
            continue

        text = ""
        missing: list[str] = []
        render_error: str | None = None
        reason_parts: list[str] = []

        prev_idx = effective_index_by_identifier.get(b.identifier)
        prev_state = block_states[prev_idx] if prev_idx is not None and prev_idx < len(block_states) else None
        if prev_state is not None and bool(prev_state.get("forbid_overrides")):
            reason_parts.append("override_forbidden")
        else:
            render_values = values
            if prev_state is not None:
                original_text = str(prev_state.get("text_after") or prev_state.get("text_before") or "")
                render_values = dict(values)
                render_values["original"] = original_text
                render_values["base"] = original_text

            if b.template:
                text, missing, render_error = render_template(b.template, render_values, macro_seed=macro_seed)
                if render_error:
                    reason_parts.append("template_error")
            elif b.marker_key:
                found, marker_value = _try_get_marker_value(values, b.marker_key)
                if found:
                    text = "" if marker_value is None else str(marker_value)
                else:
                    missing = [b.marker_key]
                    text = ""

        all_missing.update(missing)

        budget = parse_json_dict(b.budget_json)
        priority = str(budget.get("priority") or "important").strip().lower()
        if priority not in priority_rank:
            priority = "important"
        max_tokens = budget.get("maxTokens", budget.get("max_tokens"))
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            max_tokens = None

        tokens_before = estimate_tokens(text)
        text_after = text
        trimmed = False
        if max_tokens is not None and tokens_before > max_tokens:
            text_after = trim_text_to_tokens(text_after, max_tokens)
            trimmed = True
            reason_parts.append(f"block_max_tokens:{max_tokens}")
        tokens_after = estimate_tokens(text_after)

        block_states.append(
            {
                "id": b.id,
                "identifier": b.identifier,
                "role": b.role,
                "enabled": b.enabled,
                "missing": missing,
                "render_error": render_error,
                "priority": priority,
                "max_tokens": max_tokens,
                "injection_position": str(b.injection_position or "relative"),
                "injection_depth": (int(b.injection_depth) if b.injection_depth is not None else None),
                "order": int(b.injection_order or 0),
                "text_before": text,
                "tokens_before": tokens_before,
                "text_after": text_after,
                "tokens_after": tokens_after,
                "trimmed": trimmed,
                "dropped": False,
                "reason": ";".join(reason_parts) if reason_parts else None,
                "forbid_overrides": bool(b.forbid_overrides),
            }
        )

        # Handle overrides: later blocks with the same identifier supersede earlier ones.
        if prev_state is not None:
            if bool(prev_state.get("forbid_overrides")):
                # Keep the previous effective block; drop this one.
                block_states[-1]["text_after"] = ""
                block_states[-1]["tokens_after"] = 0
                block_states[-1]["dropped"] = True
                block_states[-1]["reason"] = (str(block_states[-1].get("reason")) + ";" if block_states[-1].get("reason") else "") + "override_forbidden"
                continue

            prev_state["text_after"] = ""
            prev_state["tokens_after"] = 0
            prev_state["dropped"] = True
            prev_state["reason"] = (str(prev_state.get("reason")) + ";" if prev_state.get("reason") else "") + "overridden"

        effective_index_by_identifier[b.identifier] = len(block_states) - 1

    total_tokens = sum(int(s["tokens_after"]) for s in block_states)
    if budget_tokens is not None and total_tokens > budget_tokens:
        candidates = [s for s in block_states if s["priority"] in ("drop_first", "optional", "important")]
        candidates.sort(key=lambda s: (priority_rank.get(str(s["priority"]), 2), -int(s.get("order") or 0)))
        for s in candidates:
            if total_tokens <= budget_tokens:
                break
            if not str(s.get("text_after") or "").strip():
                continue
            if s["priority"] == "must":
                continue
            total_tokens -= int(s["tokens_after"])
            s["text_after"] = ""
            s["tokens_after"] = 0
            s["dropped"] = True
            s["reason"] = (str(s["reason"]) + ";" if s.get("reason") else "") + "dropped_for_budget"

        if total_tokens > budget_tokens:
            trim_candidates = [s for s in block_states if int(s["tokens_after"]) > 0 and str(s.get("text_after") or "").strip()]
            trim_candidates.sort(key=lambda s: (priority_rank.get(str(s["priority"]), 2), -int(s.get("order") or 0)))
            for s in trim_candidates:
                if total_tokens <= budget_tokens:
                    break
                need = total_tokens - budget_tokens
                current = int(s["tokens_after"])
                target = max(0, current - need)
                if target >= current:
                    continue
                trimmed_text = trim_text_to_tokens(str(s["text_after"] or ""), target)
                new_tokens = estimate_tokens(trimmed_text)
                if new_tokens >= current:
                    continue
                total_tokens -= current - new_tokens
                s["text_after"] = trimmed_text
                s["tokens_after"] = new_tokens
                s["trimmed"] = True
                s["reason"] = (str(s["reason"]) + ";" if s.get("reason") else "") + f"trim_to_fit:{target}"

    rendered_blocks: list[RenderedBlock] = []
    relative_messages: list[ChatMessage] = []
    absolute_items: list[dict] = []
    for s in block_states:
        rendered_blocks.append(
            RenderedBlock(
                id=str(s["id"]),
                identifier=str(s["identifier"]),
                role=str(s["role"]),
                enabled=bool(s["enabled"]),
                text=str(s["text_after"] or ""),
                missing=list(s.get("missing") or []),
                token_estimate=int(s.get("tokens_after") or 0),
            )
        )
        text_after = str(s.get("text_after") or "")
        if not text_after.strip():
            continue
        msg = ChatMessage(role=normalize_role(str(s.get("role") or "")), content=text_after)
        position = str(s.get("injection_position") or "relative").strip().lower()
        depth_raw = s.get("injection_depth")
        depth = int(depth_raw) if isinstance(depth_raw, int) and depth_raw >= 0 else 0
        if position == "absolute":
            absolute_items.append({"depth": depth, "order": int(s.get("order") or 0), "msg": msg})
        else:
            relative_messages.append(msg)

    messages = list(relative_messages)
    absolute_items.sort(key=lambda item: (-int(item.get("depth") or 0), int(item.get("order") or 0)))
    for item in absolute_items:
        depth = int(item.get("depth") or 0)
        idx = max(0, len(messages) - depth)
        messages.insert(idx, item["msg"])

    system = "\n\n".join([m.content for m in messages if m.role == "system" and m.content.strip()])
    user = flatten_messages([m for m in messages if m.role != "system"])

    render_log = {
        "task": task,
        "preset_id": preset.id,
        "prompt_budget_tokens": budget_tokens,
        "prompt_tokens_estimate": total_tokens,
        "missing": sorted(all_missing),
        "blocks": [
            {
                "id": s["id"],
                "identifier": s["identifier"],
                "role": s["role"],
                "priority": s["priority"],
                "max_tokens": s["max_tokens"],
                "missing": s.get("missing") or [],
                "render_error": s.get("render_error"),
                "tokens_before": s["tokens_before"],
                "tokens_after": s["tokens_after"],
                "trimmed": s["trimmed"],
                "dropped": s["dropped"],
                "reason": s["reason"],
            }
            for s in block_states
        ],
    }

    return system, user, messages, sorted(all_missing), rendered_blocks, preset.id, render_log
