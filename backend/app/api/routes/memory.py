from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import DbDep, UserIdDep, require_owned_project
from app.core.errors import ok_payload
from app.services.memory_retrieval_service import retrieve_memory_context_pack

router = APIRouter()


@router.get("/projects/{project_id}/memory/retrieve")
def retrieve_project_memory(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    pack = retrieve_memory_context_pack(db=db, project_id=project_id)
    return ok_payload(request_id=request_id, data=pack.model_dump())

