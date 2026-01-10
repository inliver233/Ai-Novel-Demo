from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import ok_payload
from app.db.session import SessionLocal
from app.services.fractal_memory_service import get_fractal_context, rebuild_fractal_memory

router = APIRouter()


class FractalRebuildRequest(BaseModel):
    reason: str = Field(default="manual_rebuild", max_length=64)


@router.get("/projects/{project_id}/fractal")
def get_fractal(request: Request, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    db = SessionLocal()
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
        out = get_fractal_context(db=db, project_id=project_id, enabled=True)
    finally:
        db.close()
    return ok_payload(request_id=request_id, data={"result": out})


@router.post("/projects/{project_id}/fractal/rebuild")
def rebuild_fractal(request: Request, user_id: UserIdDep, project_id: str, body: FractalRebuildRequest) -> dict:
    request_id = request.state.request_id
    db = SessionLocal()
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)
        out = rebuild_fractal_memory(db=db, project_id=project_id, reason=body.reason)
    finally:
        db.close()
    return ok_payload(request_id=request_id, data={"result": out})

