from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import UserIdDep, require_project_editor, require_project_owner, require_project_viewer
from app.core.config import settings
from app.core.errors import ok_payload
from app.core.secrets import SecretCryptoError, decrypt_secret
from app.db.session import SessionLocal
from app.db.utils import utc_now
from app.models.project_settings import ProjectSettings
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.vector_rag_service import (
    VectorSource,
    build_project_chunks,
    ingest_chunks,
    purge_project_vectors,
    query_project,
    rebuild_project,
    vector_rag_status,
)

router = APIRouter()


def _ensure_settings_row(db, *, project_id: str) -> ProjectSettings:
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id)
        db.add(row)
        db.flush()
    return row


def _index_state(row: ProjectSettings | None) -> dict[str, object]:
    if row is None:
        return {"dirty": False, "last_build_at": None}
    last_build_at = getattr(row, "last_vector_build_at", None)
    return {
        "dirty": bool(getattr(row, "vector_index_dirty", False)),
        "last_build_at": last_build_at.isoformat() if last_build_at else None,
    }


def _vector_embedding_overrides(row: ProjectSettings | None) -> dict[str, str | None]:
    if row is None:
        return {}
    out: dict[str, str | None] = {}
    provider = str(getattr(row, "vector_embedding_provider", "") or "").strip()
    if provider:
        out["provider"] = provider
    base_url = str(row.vector_embedding_base_url or "").strip()
    if base_url:
        out["base_url"] = base_url
    model = str(row.vector_embedding_model or "").strip()
    if model:
        out["model"] = model
    azure_deployment = str(getattr(row, "vector_embedding_azure_deployment", "") or "").strip()
    if azure_deployment:
        out["azure_deployment"] = azure_deployment
    azure_api_version = str(getattr(row, "vector_embedding_azure_api_version", "") or "").strip()
    if azure_api_version:
        out["azure_api_version"] = azure_api_version
    st_model = str(getattr(row, "vector_embedding_sentence_transformers_model", "") or "").strip()
    if st_model:
        out["sentence_transformers_model"] = st_model
    if row.vector_embedding_api_key_ciphertext:
        try:
            api_key = decrypt_secret(row.vector_embedding_api_key_ciphertext).strip()
        except SecretCryptoError:
            api_key = ""
        if api_key:
            out["api_key"] = api_key
    return out


def _vector_rerank_config(row: ProjectSettings | None) -> dict[str, object]:
    override_enabled = row.vector_rerank_enabled if row is not None else None
    enabled = override_enabled if override_enabled is not None else bool(getattr(settings, "vector_rerank_enabled", False))

    override_method_raw = str(row.vector_rerank_method or "").strip() if row is not None else ""
    method = override_method_raw or "auto"

    override_top_k = row.vector_rerank_top_k if row is not None else None
    top_k = int(override_top_k) if override_top_k is not None else int(getattr(settings, "vector_max_candidates", 20) or 20)
    top_k = max(1, min(int(top_k), 1000))

    return {"enabled": bool(enabled), "method": method, "top_k": int(top_k)}


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
    rerank: dict[str, object] = {}
    index_state: dict[str, object] = {"dirty": False, "last_build_at": None}
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
        settings_row = db.get(ProjectSettings, project_id)
        embedding = _vector_embedding_overrides(settings_row)
        rerank = _vector_rerank_config(settings_row)
        index_state = _index_state(settings_row)
    finally:
        db.close()

    result = vector_rag_status(project_id=project_id, sources=body.sources, embedding=embedding, rerank=rerank)
    result["index"] = index_state
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
    if bool(result.get("enabled")) and not bool(result.get("skipped")):
        db2 = SessionLocal()
        try:
            settings_row = _ensure_settings_row(db2, project_id=project_id)
            settings_row.vector_index_dirty = False
            settings_row.last_vector_build_at = utc_now()
            db2.commit()
        finally:
            db2.close()
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/purge")
def purge_vector_index(request: Request, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    try:
        require_project_owner(db, project_id=project_id, user_id=user_id)
    finally:
        db.close()

    result = purge_project_vectors(project_id=project_id)
    return ok_payload(request_id=request_id, data={"result": result})


@router.post("/projects/{project_id}/vector/query")
def query_vector_index(request: Request, user_id: UserIdDep, project_id: str, body: VectorQueryRequest) -> dict:
    request_id = request.state.request_id

    db = SessionLocal()
    embedding: dict[str, str | None] = {}
    rerank: dict[str, object] = {}
    qp_cfg = None
    try:
        require_project_viewer(db, project_id=project_id, user_id=user_id)
        settings_row = db.get(ProjectSettings, project_id)
        embedding = _vector_embedding_overrides(settings_row)
        rerank = _vector_rerank_config(settings_row)
        qp_cfg = parse_query_preprocessing_config(
            (settings_row.query_preprocessing_json or "").strip() if settings_row is not None else None
        )
    finally:
        db.close()

    normalized, preprocess_obs = normalize_query_text(query_text=body.query_text, config=qp_cfg)
    result = query_project(project_id=project_id, query_text=normalized, sources=body.sources, embedding=embedding, rerank=rerank)
    return ok_payload(
        request_id=request_id,
        data={
            "result": result,
            "raw_query_text": body.query_text,
            "normalized_query_text": normalized,
            "preprocess_obs": preprocess_obs,
        },
    )
