from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.models.chapter import Chapter
from app.models.project_settings import ProjectSettings
from app.services.graph_auto_update_service import schedule_graph_auto_update_task
from app.services.graph_context_service import query_graph_context
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config

router = APIRouter()


class GraphQueryRequest(BaseModel):
    query_text: str = Field(default="", max_length=8000)
    hop: int = Field(default=1, ge=0, le=1)
    max_nodes: int = Field(default=40, ge=1, le=200)
    max_edges: int = Field(default=120, ge=0, le=500)
    enabled: bool = Field(default=True)


class GraphAutoUpdateRequest(BaseModel):
    chapter_id: str | None = Field(default=None, max_length=36)
    focus: str | None = Field(default=None, max_length=4000)


@router.post("/projects/{project_id}/graph/query")
def query_graph(request: Request, user_id: UserIdDep, project_id: str, body: GraphQueryRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    normalized = body.query_text
    preprocess_obs = None
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
        settings_row = db.get(ProjectSettings, project_id)
        qp_cfg = parse_query_preprocessing_config(
            (settings_row.query_preprocessing_json or "").strip() if settings_row is not None else None
        )
        normalized, preprocess_obs = normalize_query_text(query_text=body.query_text, config=qp_cfg)
        result = query_graph_context(
            db=db,
            project_id=project_id,
            query_text=normalized,
            hop=body.hop,
            max_nodes=body.max_nodes,
            max_edges=body.max_edges,
            enabled=body.enabled,
        )
    finally:
        db.close()

    return ok_payload(
        request_id=request_id,
        data={
            "result": result,
            "raw_query_text": body.query_text,
            "normalized_query_text": normalized,
            "preprocess_obs": preprocess_obs,
        },
    )


@router.post("/projects/{project_id}/graph/auto_update")
def trigger_graph_auto_update(request: Request, user_id: UserIdDep, project_id: str, body: GraphAutoUpdateRequest) -> dict:
    request_id = request.state.request_id

    chapter_id = str(body.chapter_id or "").strip()
    focus = str(body.focus or "").strip() or None
    if not chapter_id:
        raise AppError.validation(message="chapter_id 不能为空")

    db = SessionLocal()
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)

        chapter = db.get(Chapter, chapter_id)
        if chapter is None or str(getattr(chapter, "project_id", "")) != str(project_id):
            raise AppError.not_found()
        if str(getattr(chapter, "status", "") or "") != "done":
            raise AppError.conflict(
                message="仅定稿章节可进行图谱自动更新",
                details={
                    "reason": "chapter_not_done",
                    "chapter_status": str(getattr(chapter, "status", "") or ""),
                },
            )

        task_id = schedule_graph_auto_update_task(
            db=db,
            project_id=project_id,
            actor_user_id=user_id,
            request_id=request_id,
            chapter_id=chapter_id,
            chapter_token=None,
            focus=focus,
            reason="manual",
        )
        if not task_id:
            raise AppError(code="INTERNAL_ERROR", message="创建任务失败", status_code=500)
    finally:
        db.close()

    return ok_payload(request_id=request_id, data={"task_id": task_id})
