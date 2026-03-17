from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.prompt_route_mappers import _block_to_out, _preset_to_out, _resource_to_out
from app.core.errors import AppError
from app.db.utils import utc_now
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.services.prompt_preset_resources import list_available_preset_resources, load_preset_resource
from app.services.prompt_presets import (
    ensure_default_chapter_analyze_preset,
    ensure_default_chapter_preset,
    ensure_default_chapter_rewrite_preset,
    ensure_default_content_optimize_preset,
    ensure_default_outline_preset,
    ensure_default_plan_preset,
    ensure_default_post_edit_preset,
)

_PROMPT_BASELINE_ENSURERS: tuple[tuple[Any, dict[str, object]], ...] = (
    (ensure_default_plan_preset, {}),
    (ensure_default_post_edit_preset, {}),
    (ensure_default_content_optimize_preset, {}),
    (ensure_default_outline_preset, {"activate": False}),
    (ensure_default_chapter_preset, {"activate": False}),
    (ensure_default_chapter_analyze_preset, {"activate": False}),
    (ensure_default_chapter_rewrite_preset, {"activate": False}),
)


def _ensure_prompt_preset_baseline(db: Session, *, project_id: str) -> None:
    for ensurer, kwargs in _PROMPT_BASELINE_ENSURERS:
        ensurer(db, project_id=project_id, **kwargs)


def _list_prompt_preset_rows(db: Session, *, project_id: str) -> list[PromptPreset]:
    return (
        db.execute(
            select(PromptPreset)
            .where(PromptPreset.project_id == project_id)
            .order_by(PromptPreset.updated_at.desc())
        )
        .scalars()
        .all()
    )


def _list_prompt_block_rows(db: Session, *, preset_id: str) -> list[PromptBlock]:
    return (
        db.execute(
            select(PromptBlock)
            .where(PromptBlock.preset_id == preset_id)
            .order_by(PromptBlock.injection_order.asc())
        )
        .scalars()
        .all()
    )


def _require_prompt_preset(db: Session, *, preset_id: str) -> PromptPreset:
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    return preset


def _build_prompt_preset_list_payload(db: Session, *, project_id: str) -> dict[str, object]:
    _ensure_prompt_preset_baseline(db, project_id=project_id)
    presets = _list_prompt_preset_rows(db, project_id=project_id)
    return {"presets": [_preset_to_out(preset) for preset in presets]}


def _build_prompt_preset_resources_payload(db: Session, *, project_id: str) -> dict[str, object]:
    presets = db.execute(select(PromptPreset).where(PromptPreset.project_id == project_id)).scalars().all()
    by_resource_key = {str(preset.resource_key): preset for preset in presets if preset.resource_key}
    by_name = {str(preset.name): preset for preset in presets if preset.name}

    resources = []
    for key in list_available_preset_resources():
        resource = load_preset_resource(key)
        preset = by_resource_key.get(key) or by_name.get(resource.name)
        resources.append(_resource_to_out(resource, preset))
    return {"resources": resources}


def _reorder_prompt_blocks_payload(
    db: Session,
    *,
    preset: PromptPreset,
    ordered_block_ids: list[str],
) -> dict[str, object]:
    blocks = _list_prompt_block_rows(db, preset_id=preset.id)
    by_id: dict[str, PromptBlock] = {block.id: block for block in blocks}
    existing_ids = [block.id for block in blocks]
    existing_set = set(existing_ids)
    ordered_ids = list(ordered_block_ids or [])

    if len(ordered_ids) != len(existing_ids):
        raise AppError.validation(
            message=f"块顺序（ordered_block_ids）必须包含该 preset 的全部 blocks（expected={len(existing_ids)} got={len(ordered_ids)}）"
        )
    if len(set(ordered_ids)) != len(ordered_ids):
        raise AppError.validation(message="块顺序（ordered_block_ids）包含重复 block_id")

    ordered_set = set(ordered_ids)
    missing = existing_set - ordered_set
    extra = ordered_set - existing_set
    if missing or extra:
        raise AppError.validation(message="块顺序（ordered_block_ids）必须与该 preset 的 blocks 集合完全一致")

    for idx, block_id in enumerate(ordered_ids):
        by_id[block_id].injection_order = idx

    preset.updated_at = utc_now()
    db.commit()

    reordered_blocks = _list_prompt_block_rows(db, preset_id=preset.id)
    return {"blocks": [_block_to_out(block) for block in reordered_blocks]}
