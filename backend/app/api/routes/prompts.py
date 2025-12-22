from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.models.prompt_template import PromptTemplate
from app.schemas.prompt_presets import (
    PromptBlockCreate,
    PromptBlockOut,
    PromptBlockReorderRequest,
    PromptBlockUpdate,
    PromptPresetCreate,
    PromptPresetExportOut,
    PromptPresetExportPreset,
    PromptPresetImportRequest,
    PromptPresetOut,
    PromptPresetUpdate,
    PromptPreviewBlock,
    PromptPreviewOut,
    PromptPreviewRequest,
)
from app.schemas.prompts import PromptTemplateItem, PromptsPutRequest
from app.services.defaults import default_prompt_templates
from app.services.prompt_presets import (
    MIGRATED_PRESET_NAME,
    ensure_default_plan_preset,
    ensure_default_post_edit_preset,
    ensure_default_outline_preset,
    ensure_default_chapter_preset,
    ensure_migrated_prompt_preset,
    parse_json_dict,
    parse_json_list,
    render_preset_for_task,
)

router = APIRouter()


def _default_templates() -> list[PromptTemplateItem]:
    return default_prompt_templates()


@router.get("/projects/{project_id}/prompts")
def get_prompts(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    rows = db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    if not rows:
        defaults = _default_templates()
        db.add_all(
            [
                PromptTemplate(
                    id=new_id(),
                    project_id=project_id,
                    type=t.type,
                    system_template=t.system_template,
                    user_template=t.user_template,
                )
                for t in defaults
            ]
        )
        db.commit()
        rows = db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()

    templates = [
        PromptTemplateItem(
            type=r.type,
            system_template=r.system_template,
            user_template=r.user_template,
            updated_at=r.updated_at,
        ).model_dump()
        for r in rows
    ]
    return ok_payload(request_id=request_id, data={"templates": templates})


@router.put("/projects/{project_id}/prompts")
def put_prompts(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptsPutRequest) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    existing = {
        r.type: r
        for r in db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    }
    for t in body.templates:
        row = existing.get(t.type)
        if row is None:
            row = PromptTemplate(id=new_id(), project_id=project_id, type=t.type, system_template="", user_template="")
            db.add(row)
        if t.system_template is not None:
            row.system_template = t.system_template
        if t.user_template is not None:
            row.user_template = t.user_template
    db.commit()

    rows = db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    templates = [
        PromptTemplateItem(
            type=r.type,
            system_template=r.system_template,
            user_template=r.user_template,
            updated_at=r.updated_at,
        ).model_dump()
        for r in rows
    ]

    # Keep migrated preset in sync so old PromptsPage edits remain effective after M0.
    ensure_migrated_prompt_preset(db, project_id=project_id)
    return ok_payload(request_id=request_id, data={"templates": templates})


def _preset_to_out(row: PromptPreset) -> dict:
    return PromptPresetOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        scope=row.scope,
        version=row.version,
        active_for=parse_json_list(row.active_for_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


def _block_to_out(row: PromptBlock) -> dict:
    return PromptBlockOut(
        id=row.id,
        preset_id=row.preset_id,
        identifier=row.identifier,
        name=row.name,
        role=row.role,
        enabled=row.enabled,
        template=row.template,
        marker_key=row.marker_key,
        injection_position=row.injection_position,
        injection_depth=row.injection_depth,
        injection_order=row.injection_order,
        triggers=parse_json_list(row.triggers_json),
        forbid_overrides=row.forbid_overrides,
        budget=parse_json_dict(row.budget_json),
        cache=parse_json_dict(row.cache_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


@router.get("/projects/{project_id}/prompt_presets")
def list_prompt_presets(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    # Ensure baseline presets exist (idempotent).
    ensure_migrated_prompt_preset(db, project_id=project_id)
    ensure_default_plan_preset(db, project_id=project_id)
    ensure_default_post_edit_preset(db, project_id=project_id)
    # Recommended presets for learning (not auto-active for existing projects).
    ensure_default_outline_preset(db, project_id=project_id, activate=False)
    ensure_default_chapter_preset(db, project_id=project_id, activate=False)

    presets = (
        db.execute(select(PromptPreset).where(PromptPreset.project_id == project_id).order_by(PromptPreset.updated_at.desc()))
        .scalars()
        .all()
    )

    return ok_payload(request_id=request_id, data={"presets": [_preset_to_out(p) for p in presets]})


@router.post("/projects/{project_id}/prompt_presets")
def create_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptPresetCreate) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    row = PromptPreset(
        id=new_id(),
        project_id=project_id,
        name=body.name,
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
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)

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
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)

    if preset.name == MIGRATED_PRESET_NAME and body.name is not None:
        raise AppError(code="VALIDATION_ERROR", message="迁移预设不允许重命名（M0 阶段）", status_code=400)

    if body.name is not None:
        preset.name = body.name
    if body.scope is not None:
        preset.scope = body.scope
    if body.version is not None:
        preset.version = body.version
    if body.active_for is not None:
        preset.active_for_json = json.dumps(body.active_for or [], ensure_ascii=False)

    db.commit()
    db.refresh(preset)
    return ok_payload(request_id=request_id, data={"preset": _preset_to_out(preset)})


@router.delete("/prompt_presets/{preset_id}")
def delete_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)
    if preset.name == MIGRATED_PRESET_NAME:
        raise AppError(code="VALIDATION_ERROR", message="迁移预设不允许删除（M0 阶段）", status_code=400)

    db.delete(preset)
    db.commit()
    return ok_payload(request_id=request_id, data={})


@router.post("/prompt_presets/{preset_id}/blocks")
def create_prompt_block(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str, body: PromptBlockCreate) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)

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
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)

    if preset.name == MIGRATED_PRESET_NAME:
        raise AppError(code="VALIDATION_ERROR", message="迁移预设不允许编辑块（M0 阶段）", status_code=400)

    if body.identifier is not None:
        block.identifier = body.identifier
    if body.name is not None:
        block.name = body.name
    if body.role is not None:
        block.role = body.role
    if body.enabled is not None:
        block.enabled = body.enabled
    if body.template is not None:
        block.template = body.template
    if body.marker_key is not None:
        block.marker_key = body.marker_key
    if body.injection_position is not None:
        block.injection_position = body.injection_position
    if body.injection_depth is not None:
        block.injection_depth = body.injection_depth
    if body.injection_order is not None:
        block.injection_order = body.injection_order
    if body.triggers is not None:
        block.triggers_json = json.dumps(body.triggers or [], ensure_ascii=False)
    if body.forbid_overrides is not None:
        block.forbid_overrides = body.forbid_overrides
    if body.budget is not None:
        block.budget_json = json.dumps(body.budget or {}, ensure_ascii=False) if body.budget else None
    if body.cache is not None:
        block.cache_json = json.dumps(body.cache or {}, ensure_ascii=False) if body.cache else None

    db.commit()
    db.refresh(block)
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
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)

    if preset.name == MIGRATED_PRESET_NAME:
        raise AppError(code="VALIDATION_ERROR", message="迁移预设不允许编辑块（M0 阶段）", status_code=400)

    db.delete(block)
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
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)
    if preset.name == MIGRATED_PRESET_NAME:
        raise AppError(code="VALIDATION_ERROR", message="迁移预设不允许编辑块（M0 阶段）", status_code=400)

    blocks = (
        db.execute(select(PromptBlock).where(PromptBlock.preset_id == preset_id).order_by(PromptBlock.injection_order.asc()))
        .scalars()
        .all()
    )
    by_id: dict[str, PromptBlock] = {b.id: b for b in blocks}
    for idx, block_id in enumerate(body.ordered_block_ids):
        block = by_id.get(block_id)
        if block is None:
            raise AppError.validation(message="ordered_block_ids 包含不属于该 preset 的 block_id")
        block.injection_order = idx

    db.commit()
    blocks = (
        db.execute(select(PromptBlock).where(PromptBlock.preset_id == preset_id).order_by(PromptBlock.injection_order.asc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"blocks": [_block_to_out(b) for b in blocks]})


@router.get("/prompt_presets/{preset_id}/export")
def export_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, preset_id: str) -> dict:
    request_id = request.state.request_id
    preset = db.get(PromptPreset, preset_id)
    if preset is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=preset.project_id, user_id=user_id)

    blocks = (
        db.execute(select(PromptBlock).where(PromptBlock.preset_id == preset_id).order_by(PromptBlock.injection_order.asc()))
        .scalars()
        .all()
    )

    export_obj = PromptPresetExportOut(
        preset=PromptPresetExportPreset(
            name=preset.name,
            scope=preset.scope,
            version=preset.version,
            active_for=parse_json_list(preset.active_for_json),
        ),
        blocks=[
            {
                "identifier": b.identifier,
                "name": b.name,
                "role": b.role,
                "enabled": b.enabled,
                "template": b.template,
                "marker_key": b.marker_key,
                "injection_position": b.injection_position,
                "injection_depth": b.injection_depth,
                "injection_order": b.injection_order,
                "triggers": parse_json_list(b.triggers_json),
                "forbid_overrides": b.forbid_overrides,
                "budget": parse_json_dict(b.budget_json),
                "cache": parse_json_dict(b.cache_json),
            }
            for b in blocks
        ],
    ).model_dump()

    return ok_payload(request_id=request_id, data={"export": export_obj})


@router.post("/projects/{project_id}/prompt_presets/import")
def import_prompt_preset(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptPresetImportRequest) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    preset = PromptPreset(
        id=new_id(),
        project_id=project_id,
        name=body.preset.name,
        scope=body.preset.scope,
        version=body.preset.version,
        active_for_json=json.dumps(body.preset.active_for or [], ensure_ascii=False),
    )
    db.add(preset)
    db.flush()
    for b in body.blocks:
        db.add(
            PromptBlock(
                id=new_id(),
                preset_id=preset.id,
                identifier=b.identifier,
                name=b.name,
                role=b.role,
                enabled=b.enabled,
                template=b.template,
                marker_key=b.marker_key,
                injection_position=b.injection_position,
                injection_depth=b.injection_depth,
                injection_order=b.injection_order,
                triggers_json=json.dumps(b.triggers or [], ensure_ascii=False),
                forbid_overrides=b.forbid_overrides,
                budget_json=json.dumps(b.budget or {}, ensure_ascii=False) if b.budget else None,
                cache_json=json.dumps(b.cache or {}, ensure_ascii=False) if b.cache else None,
            )
        )
    db.commit()
    db.refresh(preset)
    return ok_payload(request_id=request_id, data={"preset": _preset_to_out(preset)})


@router.post("/projects/{project_id}/prompt_preview")
def preview_prompt(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptPreviewRequest) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    system, user, _, missing, blocks, preset_id, render_log = render_preset_for_task(
        db,
        project_id=project_id,
        task=body.task,
        values=body.values,
        preset_id=body.preset_id,
        macro_seed=request_id,
    )

    payload = PromptPreviewOut(
        preset_id=preset_id,
        task=body.task,
        system=system,
        user=user,
        prompt_tokens_estimate=int(render_log.get("prompt_tokens_estimate") or 0),
        prompt_budget_tokens=(int(render_log["prompt_budget_tokens"]) if isinstance(render_log.get("prompt_budget_tokens"), int) else None),
        missing=missing,
        blocks=[
            PromptPreviewBlock(
                id=b.id,
                identifier=b.identifier,
                role=b.role,
                enabled=b.enabled,
                text=b.text,
                missing=b.missing,
                token_estimate=b.token_estimate,
            )
            for b in blocks
        ],
    ).model_dump()
    return ok_payload(request_id=request_id, data={"preview": payload, "render_log": render_log})
