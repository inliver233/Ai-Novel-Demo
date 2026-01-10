from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_chapter_editor, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.models.structured_memory import (
    MemoryChangeSet,
    MemoryEntity,
    MemoryEvidence,
    MemoryEvent,
    MemoryForeshadow,
    MemoryRelation,
)
from app.schemas.memory_update import MemoryUpdateV1Request
from app.services.memory_retrieval_service import retrieve_memory_context_pack
from app.services.memory_update_service import apply_memory_change_set, propose_chapter_memory_change_set, rollback_memory_change_set

router = APIRouter()


@router.get("/projects/{project_id}/memory/retrieve")
def retrieve_project_memory(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    pack = retrieve_memory_context_pack(db=db, project_id=project_id)
    return ok_payload(request_id=request_id, data=pack.model_dump())


def _safe_json(raw: str | None, default: object) -> object:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


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
) -> dict:
    request_id = request.state.request_id
    chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
    out = propose_chapter_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, chapter=chapter, payload=body)
    return ok_payload(request_id=request_id, data=out)


@router.post("/memory_change_sets/{change_set_id}/apply")
def apply_memory_update(
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
    out = apply_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, change_set=change_set)
    return ok_payload(request_id=request_id, data=out)


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
