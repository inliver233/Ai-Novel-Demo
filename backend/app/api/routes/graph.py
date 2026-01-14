from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_viewer
from app.core.errors import ok_payload
from app.db.session import SessionLocal
from app.models.project_settings import ProjectSettings
from app.services.graph_context_service import query_graph_context
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config

router = APIRouter()


class GraphQueryRequest(BaseModel):
    query_text: str = Field(default="", max_length=8000)
    hop: int = Field(default=1, ge=0, le=1)
    max_nodes: int = Field(default=40, ge=1, le=200)
    max_edges: int = Field(default=120, ge=0, le=500)
    enabled: bool = Field(default=True)


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
