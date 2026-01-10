from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import DbDep, UserIdDep, require_chapter_editor, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.models.structured_memory import MemoryChangeSet
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
