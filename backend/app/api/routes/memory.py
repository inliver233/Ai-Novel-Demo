from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Query, Request
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_chapter_editor, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.llm_preset import LLMPreset
from app.models.memory_task import MemoryTask
from app.models.project import Project
from app.models.structured_memory import (
    MemoryChangeSet,
    MemoryEntity,
    MemoryEvidence,
    MemoryEvent,
    MemoryForeshadow,
    MemoryRelation,
)
from app.models.user import User
from app.schemas.base import RequestModel
from app.schemas.memory_update import MemoryUpdateV1Request
from app.schemas.memory_preview import MemoryPreviewRequest
from app.services.generation_service import call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.memory_retrieval_service import retrieve_memory_context_pack
from app.services.memory_update_service import (
    apply_memory_change_set,
    list_memory_change_sets,
    list_memory_tasks,
    memory_task_to_dict,
    propose_chapter_memory_change_set,
    rollback_memory_change_set,
)
from app.services.output_contracts import contract_for_task
from app.services.prompt_presets import _ensure_default_preset_from_resource, render_preset_for_task

router = APIRouter()
logger = logging.getLogger("ainovel")


def _require_chapter_done_for_memory_update(*, db: DbDep, chapter: Chapter, user_id: str, allow_draft: bool) -> None:
    status = str(getattr(chapter, "status", "") or "").strip().lower()
    if status == "done":
        return

    if allow_draft:
        actor = db.get(User, user_id)
        if actor is None or not bool(getattr(actor, "is_admin", False)):
            raise AppError.forbidden()
        return

    raise AppError.conflict(
        message="仅定稿章节可进行记忆更新",
        details={"reason": "chapter_not_done", "chapter_status": str(getattr(chapter, "status", "") or "")},
    )


@router.get("/projects/{project_id}/memory/retrieve")
def retrieve_project_memory(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    query_text: str = Query(default="", max_length=5000),
    include_deleted: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    pack = retrieve_memory_context_pack(db=db, project_id=project_id, query_text=query_text, include_deleted=include_deleted)
    return ok_payload(request_id=request_id, data=pack.model_dump())


@router.post("/projects/{project_id}/memory/preview")
def preview_project_memory(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: MemoryPreviewRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    pack = retrieve_memory_context_pack(
        db=db,
        project_id=project_id,
        query_text=body.query_text,
        include_deleted=False,
        section_enabled=body.section_enabled,
        budget_overrides=body.budget_overrides,
    )
    return ok_payload(request_id=request_id, data=pack.model_dump())


def _safe_json(raw: str | None, default: object) -> object:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


class MemoryAutoProposeRequest(RequestModel):
    idempotency_key: str | None = Field(default=None, max_length=64)
    focus: str | None = Field(default=None, max_length=4000)


@router.get("/projects/{project_id}/memory/structured")
def list_structured_memory(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    entities_q = select(MemoryEntity).where(MemoryEntity.project_id == project_id)
    relations_q = select(MemoryRelation).where(MemoryRelation.project_id == project_id)
    events_q = select(MemoryEvent).where(MemoryEvent.project_id == project_id)
    foreshadows_q = select(MemoryForeshadow).where(MemoryForeshadow.project_id == project_id)
    evidence_q = select(MemoryEvidence).where(MemoryEvidence.project_id == project_id)

    if not include_deleted:
        entities_q = entities_q.where(MemoryEntity.deleted_at.is_(None))
        relations_q = relations_q.where(MemoryRelation.deleted_at.is_(None))
        events_q = events_q.where(MemoryEvent.deleted_at.is_(None))
        foreshadows_q = foreshadows_q.where(MemoryForeshadow.deleted_at.is_(None))
        evidence_q = evidence_q.where(MemoryEvidence.deleted_at.is_(None))

    entities = db.execute(entities_q.order_by(MemoryEntity.updated_at.desc()).limit(limit)).scalars().all()
    relations = db.execute(relations_q.order_by(MemoryRelation.updated_at.desc()).limit(limit)).scalars().all()
    events = db.execute(events_q.order_by(MemoryEvent.updated_at.desc()).limit(limit)).scalars().all()
    foreshadows = db.execute(foreshadows_q.order_by(MemoryForeshadow.updated_at.desc()).limit(limit)).scalars().all()
    evidence = db.execute(evidence_q.order_by(MemoryEvidence.created_at.desc()).limit(limit)).scalars().all()

    data = {
        "entities": [
            {
                "id": e.id,
                "project_id": e.project_id,
                "entity_type": e.entity_type,
                "name": e.name,
                "summary_md": e.summary_md,
                "attributes": _safe_json(e.attributes_json, {}),
                "deleted_at": e.deleted_at.isoformat() if e.deleted_at else None,
                "created_at": e.created_at.isoformat(),
                "updated_at": e.updated_at.isoformat(),
            }
            for e in entities
        ],
        "relations": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "from_entity_id": r.from_entity_id,
                "to_entity_id": r.to_entity_id,
                "relation_type": r.relation_type,
                "description_md": r.description_md,
                "attributes": _safe_json(r.attributes_json, {}),
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in relations
        ],
        "events": [
            {
                "id": ev.id,
                "project_id": ev.project_id,
                "chapter_id": ev.chapter_id,
                "event_type": ev.event_type,
                "title": ev.title,
                "content_md": ev.content_md,
                "attributes": _safe_json(ev.attributes_json, {}),
                "deleted_at": ev.deleted_at.isoformat() if ev.deleted_at else None,
                "created_at": ev.created_at.isoformat(),
                "updated_at": ev.updated_at.isoformat(),
            }
            for ev in events
        ],
        "foreshadows": [
            {
                "id": f.id,
                "project_id": f.project_id,
                "chapter_id": f.chapter_id,
                "resolved_at_chapter_id": f.resolved_at_chapter_id,
                "title": f.title,
                "content_md": f.content_md,
                "resolved": f.resolved,
                "attributes": _safe_json(f.attributes_json, {}),
                "deleted_at": f.deleted_at.isoformat() if f.deleted_at else None,
                "created_at": f.created_at.isoformat(),
                "updated_at": f.updated_at.isoformat(),
            }
            for f in foreshadows
        ],
        "evidence": [
            {
                "id": ev.id,
                "project_id": ev.project_id,
                "source_type": ev.source_type,
                "source_id": ev.source_id,
                "quote_md": ev.quote_md,
                "attributes": _safe_json(ev.attributes_json, {}),
                "deleted_at": ev.deleted_at.isoformat() if ev.deleted_at else None,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in evidence
        ],
    }
    data["counts"] = {
        "entities": len(data["entities"]),
        "relations": len(data["relations"]),
        "events": len(data["events"]),
        "foreshadows": len(data["foreshadows"]),
        "evidence": len(data["evidence"]),
    }
    return ok_payload(request_id=request_id, data=data)


@router.post("/chapters/{chapter_id}/memory/propose")
def propose_chapter_memory_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    chapter_id: str,
    body: MemoryUpdateV1Request,
    allow_draft: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
    _require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)
    out = propose_chapter_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, chapter=chapter, payload=body)
    return ok_payload(request_id=request_id, data=out)


@router.post("/chapters/{chapter_id}/memory/propose/auto")
def auto_propose_chapter_memory_update(
    request: Request,
    chapter_id: str,
    body: MemoryAutoProposeRequest,
    user_id: UserIdDep,
    allow_draft: bool = Query(default=False),
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    resolved_api_key = ""

    prompt_system = ""
    prompt_user = ""
    prompt_render_log_json: str | None = None
    prompt_messages = None
    llm_call = None
    project_id = ""

    focus = (body.focus or "").strip()
    idempotency_key = (body.idempotency_key or "").strip() or f"memupd-auto-{new_id()[:8]}"

    db = SessionLocal()
    try:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        _require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)
        project_id = str(chapter.project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        preset = db.get(LLMPreset, project_id)
        if preset is None:
            raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
        if x_llm_api_key and x_llm_provider and preset.provider != x_llm_provider:
            raise AppError(code="LLM_CONFIG_ERROR", message="当前项目 provider 与请求头不一致，请先保存/切换", status_code=400)

        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=x_llm_api_key)

        _ensure_default_preset_from_resource(db, project_id=project_id, resource_key="memory_update_v1", activate=True)
        values = {
            "chapter_id": str(chapter.id),
            "chapter_number": int(chapter.number),
            "chapter_title": str(chapter.title or ""),
            "chapter_plan": str(chapter.plan or ""),
            "chapter_content_md": str(chapter.content_md or ""),
            "focus": focus,
        }

        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="memory_update",
            values=values,
            macro_seed=f"{request_id}:memory_update",
            provider=preset.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)
        llm_call = prepare_llm_call(preset)
    finally:
        db.close()

    if llm_call is None:
        raise AppError(code="INTERNAL_ERROR", message="LLM 调用准备失败", status_code=500)
    if not prompt_system.strip() and not prompt_user.strip():
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 memory_update 提示词预设/提示块", status_code=400)

    llm_call = with_param_overrides(llm_call, {"temperature": 0.2, "max_tokens": 2048})
    llm_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="memory_update_auto_propose",
        api_key=str(resolved_api_key),
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
        llm_call=llm_call,
    )

    contract = contract_for_task("memory_update")
    parsed = contract.parse(llm_result.text, finish_reason=llm_result.finish_reason)
    if parsed.parse_error is not None:
        raise AppError.validation(
            message="memory_update 输出不符合 JSON 契约",
            details={
                "parse_error": parsed.parse_error,
                "warnings": parsed.warnings,
                "generation_run_id": llm_result.run_id,
                "finish_reason": llm_result.finish_reason,
            },
        )

    payload = MemoryUpdateV1Request(
        schema_version="memory_update_v1",
        idempotency_key=idempotency_key,
        title=str(parsed.data.get("title") or "Memory Update (auto)").strip() or "Memory Update (auto)",
        summary_md=str(parsed.data.get("summary_md") or "").strip() or None,
        ops=list(parsed.data.get("ops") or []),
    )

    db2 = SessionLocal()
    try:
        chapter2 = require_chapter_editor(db2, chapter_id=chapter_id, user_id=user_id)
        _require_chapter_done_for_memory_update(db=db2, chapter=chapter2, user_id=user_id, allow_draft=allow_draft)
        out = propose_chapter_memory_change_set(
            db=db2,
            request_id=request_id,
            actor_user_id=user_id,
            chapter=chapter2,
            payload=payload,
        )
        out["llm_generation_run_id"] = llm_result.run_id
    finally:
        db2.close()
    return ok_payload(request_id=request_id, data=out)


@router.post("/memory_change_sets/{change_set_id}/apply")
def apply_memory_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    change_set_id: str,
    allow_draft: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    change_set = db.get(MemoryChangeSet, change_set_id)
    if change_set is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(change_set.project_id), user_id=user_id)

    run = db.get(GenerationRun, str(change_set.generation_run_id)) if change_set.generation_run_id else None
    chapter_id = str(getattr(run, "chapter_id", "") or "").strip()
    if chapter_id:
        chapter = db.get(Chapter, chapter_id)
        if chapter is not None:
            _require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)

    out = apply_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, change_set=change_set)
    return ok_payload(request_id=request_id, data=out)


@router.get("/projects/{project_id}/memory_change_sets")
def list_project_memory_change_sets(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    status: str | None = Query(default=None, max_length=16),
    before: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    out = list_memory_change_sets(db=db, project_id=project_id, status=status, before=before, limit=limit)
    return ok_payload(request_id=request_id, data=out)


@router.get("/projects/{project_id}/memory_tasks")
def list_project_memory_tasks(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    status: str | None = Query(default=None, max_length=16),
    before: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    out = list_memory_tasks(db=db, project_id=project_id, status=status, before=before, limit=limit)
    return ok_payload(request_id=request_id, data=out)


@router.get("/memory_tasks/{task_id}")
def get_memory_task(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(MemoryTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_viewer(db, project_id=str(task.project_id), user_id=user_id)
    return ok_payload(request_id=request_id, data=memory_task_to_dict(task=task))


@router.post("/memory_change_sets/{change_set_id}/rollback")
def rollback_memory_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    change_set_id: str,
) -> dict:
    request_id = request.state.request_id
    change_set = db.get(MemoryChangeSet, change_set_id)
    if change_set is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(change_set.project_id), user_id=user_id)
    out = rollback_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, change_set=change_set)
    return ok_payload(request_id=request_id, data=out)
