from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_project_editor
from app.api.routes.prompt_route_helpers import (
    _build_prompt_preset_list_payload,
    _build_prompt_preset_resources_payload,
    _reorder_prompt_blocks_payload,
    _require_prompt_preset,
)
from app.api.routes.prompt_route_import_export import (
    _build_prompt_import_all_payload,
    _build_prompt_preset_export_payload,
    _build_prompt_presets_export_all_payload,
    _import_prompt_preset_payload,
)
from app.api.routes.prompt_route_mappers import _block_to_out, _preset_to_out
from app.api.routes.prompt_route_preview import _build_prompt_preview_response
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id, utc_now
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.schemas.prompt_presets import (
    PromptBlockCreate,
    PromptBlockReorderRequest,
    PromptBlockUpdate,
    PromptPresetCreate,
    PromptPresetImportAllRequest,
    PromptPresetImportRequest,
    PromptPresetUpdate,
    PromptPreviewRequest,
)
from app.services.prompt_presets import (
    parse_json_dict,
    parse_json_list,
    reset_prompt_block_to_default_resource,
    reset_prompt_preset_to_default_resource,
)

router = APIRouter()


@router.get("/projects/{project_id}/prompt_presets")
def list_prompt_presets(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_prompt_preset_list_payload(db, project_id=project_id))


@router.get("/projects/{project_id}/prompt_preset_resources")
def list_prompt_preset_resources(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_prompt_preset_resources_payload(db, project_id=project_id))


@router.post("/projects/{project_id}/prompt_presets")
def create_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptPresetCreate) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    row = PromptPreset(
        id=new_id(),
        project_id=project_id,
        name=body.name,
        category=body.category,
        scope=body.scope,
        version=body.version,
        active_for_json=json.dumps(body.active_for or [], ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"preset": _preset_to_out(row)})


@router.get("/prompt_presets/{preset_id}")
def get_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)

    blocks = (
        db.execute(select(PromptBlock).where(PromptBlock.preset_id == preset_id).order_by(PromptBlock.injection_order.asc()))
        .scalars()
        .all()
    )
    return ok_payload(
        request_id=request_id,
        data={"preset": _preset_to_out(preset), "blocks": [_block_to_out(b) for b in blocks]},
    )


@router.put("/prompt_presets/{preset_id}")
def update_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str, body: PromptPresetUpdate) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)

    if body.name is not None:
        preset.name = body.name
    if "category" in body.model_fields_set:
        preset.category = body.category
    if body.scope is not None:
        preset.scope = body.scope
    if body.version is not None:
        preset.version = body.version
    if body.active_for is not None:
        preset.active_for_json = json.dumps(body.active_for or [], ensure_ascii=False)

    db.commit()
    db.refresh(preset)
    return ok_payload(request_id=request_id, data={"preset": _preset_to_out(preset)})


@router.post("/prompt_presets/{preset_id}/reset_to_default")
def reset_prompt_preset_to_default(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)

    preset = reset_prompt_preset_to_default_resource(db, preset=preset)
    blocks = (
        db.execute(select(PromptBlock).where(PromptBlock.preset_id == preset.id).order_by(PromptBlock.injection_order.asc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"preset": _preset_to_out(preset), "blocks": [_block_to_out(b) for b in blocks]})


@router.delete("/prompt_presets/{preset_id}")
def delete_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)
    db.delete(preset)
    db.commit()
    return ok_payload(request_id=request_id, data={})


@router.post("/prompt_presets/{preset_id}/blocks")
def create_prompt_block(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str, body: PromptBlockCreate) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)
    row = PromptBlock(
        id=new_id(),
        preset_id=preset_id,
        identifier=body.identifier,
        name=body.name,
        role=body.role,
        enabled=body.enabled,
        template=body.template,
        marker_key=body.marker_key,
        injection_position=body.injection_position,
        injection_depth=body.injection_depth,
        injection_order=body.injection_order,
        triggers_json=json.dumps(body.triggers or [], ensure_ascii=False),
        forbid_overrides=body.forbid_overrides,
        budget_json=json.dumps(body.budget or {}, ensure_ascii=False) if body.budget else None,
        cache_json=json.dumps(body.cache or {}, ensure_ascii=False) if body.cache else None,
    )
    db.add(row)
    preset.updated_at = utc_now()
    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"block": _block_to_out(row)})


@router.put("/prompt_blocks/{block_id}")
def update_prompt_block(request: Request, db: DbDep, user_id: UserIdDep, block_id: str, body: PromptBlockUpdate) -> dict:
    request_id = request.state.request_id
    block = db.get(PromptBlock, block_id)
    if block is None:
        raise AppError.not_found()
    preset = db.get(PromptPreset, block.preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)

    if body.identifier is not None:
        block.identifier = body.identifier
    if body.name is not None:
        block.name = body.name
    if body.role is not None:
        block.role = body.role
    if body.enabled is not None:
        block.enabled = body.enabled
    if "template" in body.model_fields_set:
        block.template = body.template
    if "marker_key" in body.model_fields_set:
        block.marker_key = body.marker_key
    if body.injection_position is not None:
        block.injection_position = body.injection_position
    if "injection_depth" in body.model_fields_set:
        block.injection_depth = body.injection_depth
    if body.injection_order is not None:
        block.injection_order = body.injection_order
    if "triggers" in body.model_fields_set:
        block.triggers_json = json.dumps(body.triggers or [], ensure_ascii=False) if body.triggers is not None else None
    if body.forbid_overrides is not None:
        block.forbid_overrides = body.forbid_overrides
    if body.budget is not None:
        block.budget_json = json.dumps(body.budget or {}, ensure_ascii=False) if body.budget else None
    if body.cache is not None:
        block.cache_json = json.dumps(body.cache or {}, ensure_ascii=False) if body.cache else None

    preset.updated_at = utc_now()
    db.commit()
    db.refresh(block)
    return ok_payload(request_id=request_id, data={"block": _block_to_out(block)})


@router.post("/prompt_blocks/{block_id}/reset_to_default")
def reset_prompt_block_to_default(request: Request, db: DbDep, user_id: UserIdDep, block_id: str) -> dict:
    request_id = request.state.request_id
    block = db.get(PromptBlock, block_id)
    if block is None:
        raise AppError.not_found()
    preset = db.get(PromptPreset, block.preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)

    block = reset_prompt_block_to_default_resource(db, preset=preset, block=block)
    return ok_payload(request_id=request_id, data={"block": _block_to_out(block)})


@router.delete("/prompt_blocks/{block_id}")
def delete_prompt_block(request: Request, db: DbDep, user_id: UserIdDep, block_id: str) -> dict:
    request_id = request.state.request_id
    block = db.get(PromptBlock, block_id)
    if block is None:
        raise AppError.not_found()
    preset = db.get(PromptPreset, block.preset_id)
    if preset is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)

    db.delete(block)
    preset.updated_at = utc_now()
    db.commit()
    return ok_payload(request_id=request_id, data={})


@router.post("/prompt_presets/{preset_id}/blocks/reorder")
def reorder_prompt_blocks(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    preset_id: str,
    body: PromptBlockReorderRequest,
) -> dict:
    request_id = request.state.request_id
    preset = _require_prompt_preset(db, preset_id=preset_id)
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_reorder_prompt_blocks_payload(db, preset=preset, ordered_block_ids=list(body.ordered_block_ids or [])),
    )


@router.get("/prompt_presets/{preset_id}/export")
def export_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str) -> dict:
    request_id = request.state.request_id
    preset = _require_prompt_preset(db, preset_id=preset_id)
    require_project_editor(db, project_id=preset.project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_prompt_preset_export_payload(db, preset=preset))


@router.post("/projects/{project_id}/prompt_presets/import")
def import_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptPresetImportRequest) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_import_prompt_preset_payload(db, project_id=project_id, body=body))


@router.get("/projects/{project_id}/prompt_presets/export_all")
def export_all_prompt_presets(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_prompt_presets_export_all_payload(db, project_id=project_id))


@router.post("/projects/{project_id}/prompt_presets/import_all")
def import_all_prompt_presets(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: PromptPresetImportAllRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(request_id=request_id, data=_build_prompt_import_all_payload(db, project_id=project_id, body=body))


@router.post("/projects/{project_id}/prompt_preview")
def preview_prompt(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptPreviewRequest) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    return ok_payload(
        request_id=request_id,
        data=_build_prompt_preview_response(db, project_id=project_id, request_id=request_id, body=body),
    )
