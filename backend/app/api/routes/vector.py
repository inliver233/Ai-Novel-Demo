from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import ok_payload
from app.db.session import SessionLocal
from app.services.vector_rag_service import VectorSource, build_project_chunks, ingest_chunks, query_project, rebuild_project

router = APIRouter()


class VectorIngestRequest(BaseModel):
    sources: list[VectorSource] = Field(default_factory=lambda: ["worldbook", "outline", "chapter"], max_length=10)


class VectorQueryRequest(BaseModel):
    query_text: str = Field(default="", max_length=8000)
    sources: list[VectorSource] = Field(default_factory=lambda: ["worldbook", "outline", "chapter"], max_length=10)


@router.post("/projects/{project_id}/vector/ingest")
def ingest_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorIngestRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)
        chunks = build_project_chunks(db=db, project_id=project_id, sources=body.sources)
    finally:
        db.close()

    result = ingest_chunks(project_id=project_id, chunks=chunks)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/rebuild")
def rebuild_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorIngestRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)
        chunks = build_project_chunks(db=db, project_id=project_id, sources=body.sources)
    finally:
        db.close()

    result = rebuild_project(project_id=project_id, chunks=chunks)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/query")
def query_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorQueryRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
    finally:
        db.close()

    result = query_project(project_id=project_id, query_text=body.query_text, sources=body.sources)
    return ok_payload(request_id=request_id, data={"result": result})
