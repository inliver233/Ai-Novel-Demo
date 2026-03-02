from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.utils import new_id, utc_now
from app.llm.capabilities import max_context_tokens_limit, max_output_tokens_limit
from app.llm.messages import ChatMessage, flatten_messages, normalize_role
from app.models.llm_preset import LLMPreset
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.services.context_optimizer import ContextOptimizer
from app.services.prompt_budget import estimate_tokens, trim_text_to_tokens
from app.services.prompt_preset_resources import list_available_preset_resources, load_preset_resource
from app.services.prompting import render_template


LEGACY_IMPORTED_SCOPE = "legacy_imported"
DEFAULT_PLAN_PRESET_NAME = "Default plan_chapter v1"
DEFAULT_POST_EDIT_PRESET_NAME = "Default post_edit v1"
DEFAULT_CONTENT_OPTIMIZE_PRESET_NAME = "Default content_optimize v1"
DEFAULT_OUTLINE_PRESET_NAME = "默认·大纲生成 v3（推荐）"
DEFAULT_CHAPTER_PRESET_NAME = "默认·章节生成 v3（推荐）"
DEFAULT_CHAPTER_ANALYZE_PRESET_NAME = "默认·章节分析 v1（推荐）"
DEFAULT_CHAPTER_REWRITE_PRESET_NAME = "默认·章节重写 v1（推荐）"

_PROMPT_BLOCK_RENDER_CACHE_MAX_ENTRIES = 512
_prompt_block_render_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_prompt_block_render_cache_lock = Lock()


def _hash_json(value: Any) -> str | None:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _prompt_block_cache_get(key: str, *, ttl_seconds: int | None) -> tuple[dict[str, Any] | None, str]:
    now = time.time()
    with _prompt_block_render_cache_lock:
        entry = _prompt_block_render_cache.get(key)
        if entry is None:
            return None, "miss"
        created_at, payload = entry
        if isinstance(ttl_seconds, int) and ttl_seconds > 0 and now - created_at > ttl_seconds:
            del _prompt_block_render_cache[key]
            return None, "expired"
        _prompt_block_render_cache.move_to_end(key, last=True)
        return payload, "hit"


def _prompt_block_cache_set(key: str, *, payload: dict[str, Any]) -> None:
    now = time.time()
    with _prompt_block_render_cache_lock:
        _prompt_block_render_cache[key] = (now, payload)
        _prompt_block_render_cache.move_to_end(key, last=True)
        while len(_prompt_block_render_cache) > _PROMPT_BLOCK_RENDER_CACHE_MAX_ENTRIES:
            _prompt_block_render_cache.popitem(last=False)


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
        db.execute(select(PromptPreset).where(PromptPreset.project_id == project_id, PromptPreset.resource_key == resource_key))
        .scalars()
        .first()
    )
    if preset is None:
        preset = (
            db.execute(select(PromptPreset).where(PromptPreset.project_id == project_id, PromptPreset.name == resource.name))
            .scalars()
            .first()
        )

    changed = False
    if preset is not None:
        if not preset.resource_key:
            preset.resource_key = resource_key
            changed = True

        if not preset.category and resource.category:
            preset.category = resource.category
            changed = True

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
        resource_key=resource_key,
        category=resource.category,
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


def ensure_default_content_optimize_preset(db: Session, *, project_id: str) -> PromptPreset:
    return _ensure_default_preset_from_resource(
        db, project_id=project_id, resource_key="content_optimize_v1", activate=True
    )


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
        resource_key="chapter_generate_v4",
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


def resolve_resource_key_for_preset(db: Session, *, preset: PromptPreset) -> str | None:
    if preset.resource_key:
        return str(preset.resource_key)

    name = str(preset.name or "").strip()
    if not name:
        return None

    for key in list_available_preset_resources():
        try:
            resource = load_preset_resource(key)
        except Exception:
            continue
        if resource.name == name:
            preset.resource_key = key
            return key
    return None


def reset_prompt_preset_to_default_resource(db: Session, *, preset: PromptPreset) -> PromptPreset:
    resource_key = resolve_resource_key_for_preset(db, preset=preset)
    if not resource_key:
        raise AppError.validation(message="该 PromptPreset 未绑定内置资源，无法重置到默认版本")

    resource = load_preset_resource(resource_key)

    preset.resource_key = resource_key
    preset.scope = resource.scope
    preset.version = resource.version
    if resource.category:
        preset.category = resource.category
    preset.updated_at = utc_now()

    existing_blocks = db.execute(select(PromptBlock).where(PromptBlock.preset_id == preset.id)).scalars().all()
    for b in existing_blocks:
        db.delete(b)
    db.flush()

    blocks = [_prompt_block_from_resource(preset.id, b) for b in resource.blocks]
    db.add_all(blocks)
    db.commit()
    db.refresh(preset)
    return preset


def reset_prompt_block_to_default_resource(db: Session, *, preset: PromptPreset, block: PromptBlock) -> PromptBlock:
    resource_key = resolve_resource_key_for_preset(db, preset=preset)
    if not resource_key:
        raise AppError.validation(message="该 PromptPreset 未绑定内置资源，无法重置 block 到默认版本")

    resource = load_preset_resource(resource_key)
    res_block = next((b for b in resource.blocks if b.identifier == block.identifier), None)
    if res_block is None:
        raise AppError.validation(
            message="该 PromptBlock 不属于内置资源，无法重置到默认版本",
            details={"resource": resource_key, "identifier": block.identifier},
        )

    block.identifier = str(res_block.identifier)
    block.name = str(res_block.name)
    block.role = str(res_block.role)
    block.enabled = bool(res_block.enabled)
    block.template = str(res_block.template or "")
    block.marker_key = res_block.marker_key
    block.injection_position = str(res_block.injection_position)
    block.injection_depth = res_block.injection_depth
    block.injection_order = int(res_block.injection_order)
    block.triggers_json = json.dumps(list(res_block.triggers or []), ensure_ascii=False)
    block.forbid_overrides = bool(res_block.forbid_overrides)
    block.budget_json = json.dumps(res_block.budget, ensure_ascii=False) if res_block.budget else None
    block.cache_json = json.dumps(res_block.cache, ensure_ascii=False) if res_block.cache else None

    preset.updated_at = utc_now()
    db.commit()
    db.refresh(block)
    return block


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
        if task == "content_optimize":
            return ensure_default_content_optimize_preset(db, project_id=project_id)
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
        "openai_responses": 24000,
        "openai_compatible": 24000,
        "openai_responses_compatible": 24000,
        "anthropic": 12000,
        "gemini": 12000,
    }
    budget_tokens = prompt_budget_tokens
    budget_source = "explicit" if budget_tokens is not None else "unset"
    budget_calc: dict[str, Any] | None = None
    if budget_tokens is None:
        llm_preset = db.get(LLMPreset, project_id)
        effective_provider = str(provider or (llm_preset.provider if llm_preset is not None else "")).strip()
        effective_model = (
            str(llm_preset.model or "").strip()
            if llm_preset is not None and (provider is None or provider == llm_preset.provider)
            else None
        )

        max_ctx = max_context_tokens_limit(effective_provider, effective_model)
        max_out = max_output_tokens_limit(effective_provider, effective_model)
        safety_margin = 512

        if isinstance(max_ctx, int) and max_ctx > 0 and isinstance(max_out, int) and max_out > 0:
            computed = int(max_ctx) - int(max_out) - int(safety_margin)
            if computed > 0:
                budget_tokens = computed
                budget_source = "capabilities"
            else:
                budget_tokens = default_budget_by_provider.get(effective_provider or "", 24000)
                budget_source = "provider_default"
            budget_calc = {
                "provider": effective_provider,
                "model": effective_model,
                "max_context_tokens": int(max_ctx),
                "max_output_tokens": int(max_out),
                "safety_margin_tokens": int(safety_margin),
                "computed_budget_tokens": int(computed),
            }
        else:
            budget_tokens = default_budget_by_provider.get(effective_provider or "", 24000)
            budget_source = "provider_default"
            budget_calc = {
                "provider": effective_provider,
                "model": effective_model,
                "max_context_tokens": int(max_ctx) if isinstance(max_ctx, int) else None,
                "max_output_tokens": int(max_out) if isinstance(max_out, int) else None,
                "safety_margin_tokens": int(safety_margin),
                "computed_budget_tokens": None,
            }

    all_missing: set[str] = set()
    block_states: list[dict] = []
    effective_index_by_identifier: dict[str, int] = {}
    cache_hit: list[dict[str, Any]] = []
    cache_miss: list[dict[str, Any]] = []

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
            base_text: str | None = None
            if prev_state is not None:
                original_text = str(prev_state.get("text_after") or prev_state.get("text_before") or "")
                base_text = original_text
                render_values = dict(values)
                render_values["original"] = original_text
                render_values["base"] = original_text

            cache_cfg = parse_json_dict(b.cache_json)
            cache_enabled = bool(cache_cfg.get("enabled", False))
            cache_ttl_seconds = cache_cfg.get("ttl_seconds", cache_cfg.get("ttl", cache_cfg.get("max_age_seconds")))
            ttl_seconds: int | None = cache_ttl_seconds if isinstance(cache_ttl_seconds, int) and cache_ttl_seconds > 0 else None

            if b.template:
                cache_key: str | None = None
                cache_status: str | None = None
                cache_reason: str | None = None
                if cache_enabled:
                    strategy = str(cache_cfg.get("key_strategy", cache_cfg.get("strategy") or "")).strip().lower() or "marker_or_values"
                    marker_key_for_cache = cache_cfg.get("marker_key")
                    marker_key = (
                        str(marker_key_for_cache).strip()
                        if isinstance(marker_key_for_cache, str) and str(marker_key_for_cache).strip()
                        else (str(b.marker_key).strip() if b.marker_key else None)
                    )

                    values_hash: str | None
                    if marker_key is not None and strategy in ("marker", "marker_key", "marker_or_values"):
                        found, marker_value = _try_get_marker_value(values, marker_key)
                        marker_hash = _hash_json(marker_value) if found else "missing"
                        values_hash = marker_hash if marker_hash is not None else None
                    else:
                        values_hash = _hash_json(values)

                    base_hash = _hash_text(base_text) if isinstance(base_text, str) else None
                    template_hash = _hash_text(str(b.template or ""))
                    seed_hash = _hash_text(str(macro_seed or ""))

                    if values_hash is None:
                        cache_status = "skip"
                        cache_reason = "unhashable_values"
                    else:
                        cache_key = f"v1|{b.id}|{task}|{template_hash}|{seed_hash}|{values_hash}|{base_hash or '-'}"
                        cached, cache_status = _prompt_block_cache_get(cache_key, ttl_seconds=ttl_seconds)
                        if cached is not None:
                            text = str(cached.get("text") or "")
                            missing = list(cached.get("missing") or [])
                            render_error = str(cached.get("render_error") or "") or None
                        else:
                            cache_reason = cache_status

                if cache_key is not None and cache_status == "hit":
                    cache_hit.append({"id": b.id, "identifier": b.identifier})
                elif cache_enabled:
                    cache_miss.append(
                        {
                            "id": b.id,
                            "identifier": b.identifier,
                            "reason": cache_reason or cache_status or "miss",
                        }
                    )

                if cache_key is None or cache_status != "hit":
                    text, missing, render_error = render_template(b.template, render_values, macro_seed=macro_seed)
                    if cache_key is not None and (render_error is None):
                        _prompt_block_cache_set(cache_key, payload={"text": text, "missing": missing, "render_error": render_error})
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

    optimizer_enabled = bool(values.get("context_optimizer_enabled", False))
    optimizer_log = ContextOptimizer(enabled=optimizer_enabled).optimize_prompt_block_states(block_states)

    def _context_group(identifier: str) -> str | None:
        if identifier.startswith("sys.story.smart_context."):
            return "smart_context"
        if identifier.startswith("sys.memory."):
            return "memory_pack"
        return None

    def _sum_context_tokens() -> dict[str, int]:
        smart = 0
        memory = 0
        for s in block_states:
            identifier = str(s.get("identifier") or "")
            tokens = int(s.get("tokens_after") or 0)
            if tokens <= 0:
                continue
            group = _context_group(identifier)
            if group == "smart_context":
                smart += tokens
            elif group == "memory_pack":
                memory += tokens
        return {"smart_context": int(smart), "memory_pack": int(memory), "total": int(smart + memory)}

    unified_cfg = values.get("unified_context_budget")
    unified_enabled = False
    unified_budget_tokens: int | None = None
    unified_budget_source = "disabled"
    if isinstance(unified_cfg, dict):
        unified_enabled = bool(unified_cfg.get("enabled"))
        raw_tokens = unified_cfg.get("budget_tokens", unified_cfg.get("total_tokens"))
        if isinstance(raw_tokens, int) and raw_tokens > 0:
            unified_budget_tokens = int(raw_tokens)
            unified_budget_source = "explicit"
        else:
            ratio_raw = unified_cfg.get("ratio")
            try:
                ratio = float(ratio_raw)  # type: ignore[arg-type]
            except Exception:
                ratio = 0.0
            if unified_enabled and ratio > 0 and ratio <= 1 and isinstance(budget_tokens, int) and budget_tokens > 0:
                unified_budget_tokens = max(0, int(int(budget_tokens) * ratio))
                if unified_budget_tokens > 0:
                    unified_budget_source = "ratio"

    unified_log: dict[str, Any] = {
        "enabled": bool(unified_enabled and isinstance(unified_budget_tokens, int) and unified_budget_tokens > 0),
        "budget_tokens": unified_budget_tokens,
        "budget_source": unified_budget_source,
        "before": _sum_context_tokens(),
        "after": None,
        "applied": False,
        "dropped_blocks": 0,
        "trimmed_blocks": 0,
    }

    if unified_log["enabled"] and isinstance(unified_budget_tokens, int) and unified_budget_tokens > 0:
        before_total = int((unified_log.get("before") or {}).get("total") or 0)
        if before_total > unified_budget_tokens:
            ctx_total = before_total
            dropped = 0
            trimmed = 0

            candidates = [
                s
                for s in block_states
                if _context_group(str(s.get("identifier") or "")) is not None
                and int(s.get("tokens_after") or 0) > 0
                and str(s.get("text_after") or "").strip()
            ]

            drop_candidates = [s for s in candidates if str(s.get("priority") or "") in ("drop_first", "optional", "important")]
            drop_candidates.sort(key=lambda s: (priority_rank.get(str(s.get("priority") or ""), 2), -int(s.get("order") or 0)))
            for s in drop_candidates:
                if ctx_total <= unified_budget_tokens:
                    break
                current = int(s.get("tokens_after") or 0)
                if current <= 0:
                    continue
                ctx_total -= current
                s["text_after"] = ""
                s["tokens_after"] = 0
                s["dropped"] = True
                s["reason"] = (str(s.get("reason") or "") + ";" if s.get("reason") else "") + "dropped_for_unified_context_budget"
                dropped += 1

            if ctx_total > unified_budget_tokens:
                trim_candidates = [
                    s for s in candidates if int(s.get("tokens_after") or 0) > 0 and str(s.get("text_after") or "").strip()
                ]
                trim_candidates.sort(
                    key=lambda s: (priority_rank.get(str(s.get("priority") or ""), 2), -int(s.get("order") or 0))
                )
                for s in trim_candidates:
                    if ctx_total <= unified_budget_tokens:
                        break
                    current = int(s.get("tokens_after") or 0)
                    if current <= 0:
                        continue
                    need = ctx_total - unified_budget_tokens
                    target = max(0, current - need)
                    trimmed_text = trim_text_to_tokens(str(s.get("text_after") or ""), target)
                    new_tokens = estimate_tokens(trimmed_text)
                    if new_tokens >= current:
                        continue
                    ctx_total -= current - new_tokens
                    s["text_after"] = trimmed_text
                    s["tokens_after"] = new_tokens
                    s["trimmed"] = True
                    s["reason"] = (str(s.get("reason") or "") + ";" if s.get("reason") else "") + f"trim_for_unified_context_budget:{target}"
                    trimmed += 1

            unified_log["applied"] = True
            unified_log["dropped_blocks"] = int(dropped)
            unified_log["trimmed_blocks"] = int(trimmed)

    unified_log["after"] = _sum_context_tokens()

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
        "context_optimizer": optimizer_log,
        "unified_context_budget": unified_log,
        "cache_hit": cache_hit,
        "cache_miss": cache_miss,
        "prompt_budget_tokens": budget_tokens,
        "prompt_budget_source": budget_source,
        "prompt_budget_calc": budget_calc,
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
