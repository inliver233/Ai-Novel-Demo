from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import ok_payload
from app.core.secrets import SecretCryptoError, decrypt_secret
from app.db.session import SessionLocal
from app.models.project_settings import ProjectSettings
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.vector_rag_service import (
    VectorSource,
    build_project_chunks,
    ingest_chunks,
    query_project,
    rebuild_project,
    vector_rag_status,
)

router = APIRouter()

def _vector_embedding_overrides(row: ProjectSettings | None) -> dict[str, str | None]:
    if row is None:
        return {}
    out: dict[str, str | None] = {}
    base_url = str(row.vector_embedding_base_url or "").strip()
    if base_url:
        out["base_url"] = base_url
    model = str(row.vector_embedding_model or "").strip()
    if model:
        out["model"] = model
    if row.vector_embedding_api_key_ciphertext:
        try:
            api_key = decrypt_secret(row.vector_embedding_api_key_ciphertext).strip()
        except SecretCryptoError:
            api_key = ""
        if api_key:
            out["api_key"] = api_key
    return out


class VectorIngestRequest(BaseModel):
    sources: list[VectorSource] = Field(default_factory=lambda: ["worldbook", "outline", "chapter"], max_length=10)


class VectorQueryRequest(BaseModel):
    query_text: str = Field(default="", max_length=8000)
    sources: list[VectorSource] = Field(default_factory=lambda: ["worldbook", "outline", "chapter"], max_length=10)


class VectorStatusRequest(BaseModel):
    sources: list[VectorSource] = Field(default_factory=lambda: ["worldbook", "outline", "chapter"], max_length=10)


@router.post("/projects/{project_id}/vector/status")
def get_vector_status(request: Request, user_id: UserIdDep, project_id: str, body: VectorStatusRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    embedding: dict[str, str | None] = {}
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
        embedding = _vector_embedding_overrides(db.get(ProjectSettings, project_id))
    finally:
        db.close()

    result = vector_rag_status(project_id=project_id, sources=body.sources, embedding=embedding)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/ingest")
def ingest_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorIngestRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    embedding: dict[str, str | None] = {}
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)
        chunks = build_project_chunks(db=db, project_id=project_id, sources=body.sources)
        embedding = _vector_embedding_overrides(db.get(ProjectSettings, project_id))
    finally:
        db.close()

    result = ingest_chunks(project_id=project_id, chunks=chunks, embedding=embedding)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/rebuild")
def rebuild_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorIngestRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    embedding: dict[str, str | None] = {}
    try:
        require_project_editor(db, project_id=project_id, user_id=user_id)
        chunks = build_project_chunks(db=db, project_id=project_id, sources=body.sources)
        embedding = _vector_embedding_overrides(db.get(ProjectSettings, project_id))
    finally:
        db.close()

    result = rebuild_project(project_id=project_id, chunks=chunks, embedding=embedding)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/query")
def query_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorQueryRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    embedding: dict[str, str | None] = {}
    qp_cfg = None
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
        settings_row = db.get(ProjectSettings, project_id)
        embedding = _vector_embedding_overrides(settings_row)
        qp_cfg = parse_query_preprocessing_config(
            (settings_row.query_preprocessing_json or "").strip() if settings_row is not None else None
        )
    finally:
        db.close()

    normalized, preprocess_obs = normalize_query_text(query_text=body.query_text, config=qp_cfg)
    result = query_project(project_id=project_id, query_text=normalized, sources=body.sources, embedding=embedding)
    return ok_payload(
        request_id=request_id,
        data={
            "result": result,
            "raw_query_text": body.query_text,
            "normalized_query_text": normalized,
            "preprocess_obs": preprocess_obs,
        },
    )
