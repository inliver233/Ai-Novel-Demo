from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.services.fractal_memory_service import get_fractal_context, rebuild_fractal_memory, rebuild_fractal_memory_v2
from app.services.generation_service import prepare_llm_call
from app.services.llm_key_resolver import resolve_api_key_for_project

router = APIRouter()
logger = logging.getLogger("ainovel")


class FractalRebuildRequest(BaseModel):
    reason: str = Field(default="manual_rebuild", max_length=64)
    mode: Literal["deterministic", "llm_v2"] = Field(default="deterministic")


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
def rebuild_fractal(
    request: Request,
    user_id: UserIdDep,
    project_id: str,
    body: FractalRebuildRequest,
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    db = SessionLocal()
    stage = "require_project_editor"
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)
        if body.mode == "llm_v2":
            stage = "resolve_project"
            project = db.get(Project, project_id)
            resolved_api_key = ""
            if project is not None:
                try:
                    stage = "resolve_api_key"
                    resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=x_llm_api_key)
                except AppError:
                    resolved_api_key = ""
            stage = "load_llm_preset"
            preset = db.get(LLMPreset, project_id)
            llm_call = prepare_llm_call(preset) if preset is not None else None
            stage = "rebuild_v2"
            out = rebuild_fractal_memory_v2(
                db=db,
                project_id=project_id,
                reason=body.reason,
                request_id=request_id,
                actor_user_id=user_id,
                api_key=str(resolved_api_key),
                llm_call=llm_call,
            )
        else:
            stage = "rebuild_deterministic"
            out = rebuild_fractal_memory(db=db, project_id=project_id, reason=body.reason)
    except AppError as exc:
        log_event(
            logger,
            "warning" if exc.status_code < 500 else "error",
            event="FRACTAL_REBUILD",
            action="failed",
            project_id=project_id,
            mode=body.mode,
            reason=body.reason,
            stage=stage,
            error_code=exc.code,
        )
        raise
    except Exception as exc:
        log_event(
            logger,
            "error",
            event="FRACTAL_REBUILD",
            action="failed",
            project_id=project_id,
            mode=body.mode,
            reason=body.reason,
            stage=stage,
            error_code="UNHANDLED_EXCEPTION",
            **exception_log_fields(exc),
        )
        raise
    finally:
        db.close()
    return ok_payload(request_id=request_id, data={"result": out})
