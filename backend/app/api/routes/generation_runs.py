from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_generation_run_viewer, require_project_viewer
from app.core.config import settings
from app.core.errors import ok_payload
from app.core.secrets import redact_api_keys
from app.llm.redaction import redact_text
from app.models.generation_run import GenerationRun
from app.models.project_settings import ProjectSettings
from app.schemas.generation_runs import GenerationRunOut
from app.services.vector_embedding_overrides import vector_embedding_overrides
from app.services.vector_rag_service import VectorSource, query_project, vector_rag_status

router = APIRouter()


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value not in ("0", "false", "False", "FALSE", "")


def _safe_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


def _safe_json_dict_or_none(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


def _vector_rerank_config(row: ProjectSettings | None) -> dict[str, object]:
    override_enabled = row.vector_rerank_enabled if row is not None else None
    enabled = override_enabled if override_enabled is not None else bool(getattr(settings, "vector_rerank_enabled", False))

    override_method_raw = str(row.vector_rerank_method or "").strip() if row is not None else ""
    method = override_method_raw or "auto"

    override_top_k = row.vector_rerank_top_k if row is not None else None
    top_k = int(override_top_k) if override_top_k is not None else int(getattr(settings, "vector_max_candidates", 20) or 20)
    top_k = max(1, min(int(top_k), 1000))

    return {"enabled": bool(enabled), "method": method, "top_k": int(top_k)}


@router.get("/projects/{project_id}/generation_runs")
def list_runs(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    limit: int = Query(default=5, ge=1, le=50),
    chapter_id: str | None = Query(default=None, max_length=36),
    run_request_id: str | None = Query(default=None, alias="request_id", max_length=64),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    q = select(GenerationRun).where(GenerationRun.project_id == project_id)
    if chapter_id:
        q = q.where(GenerationRun.chapter_id == chapter_id)
    if run_request_id:
        q = q.where(GenerationRun.request_id == run_request_id)
    rows = db.execute(q.order_by(GenerationRun.created_at.desc()).limit(limit)).scalars().all()

    def _to_out(r: GenerationRun) -> dict:
        params = {}
        if r.params_json:
            try:
                params = json.loads(r.params_json)
            except json.JSONDecodeError:
                params = {"_raw": r.params_json}
        render_log = None
        if r.prompt_render_log_json:
            try:
                render_log = json.loads(r.prompt_render_log_json)
            except json.JSONDecodeError:
                render_log = {"_raw": r.prompt_render_log_json}
        err = None
        if r.error_json:
            try:
                err = json.loads(r.error_json)
            except json.JSONDecodeError:
                err = {"_raw": r.error_json}
        return GenerationRunOut(
            id=r.id,
            project_id=r.project_id,
            actor_user_id=r.actor_user_id,
            chapter_id=r.chapter_id,
            type=r.type,
            provider=r.provider,
            model=r.model,
            request_id=r.request_id,
            prompt_system=redact_text(r.prompt_system) if r.prompt_system else None,
            prompt_user=redact_text(r.prompt_user) if r.prompt_user else None,
            prompt_render_log=render_log,
            params=params,
            output_text=r.output_text,
            error=err,
            created_at=r.created_at,
        ).model_dump()

    return ok_payload(request_id=request_id, data={"runs": [_to_out(r) for r in rows]})


@router.get("/generation_runs/{run_id}")
def get_run(request: Request, db: DbDep, user_id: UserIdDep, run_id: str) -> dict:
    request_id = request.state.request_id
    row = require_generation_run_viewer(db, run_id=run_id, user_id=user_id)
    params = {}
    if row.params_json:
        try:
            params = json.loads(row.params_json)
        except json.JSONDecodeError:
            params = {"_raw": row.params_json}
    err = None
    if row.error_json:
        try:
            err = json.loads(row.error_json)
        except json.JSONDecodeError:
            err = {"_raw": row.error_json}
    render_log = None
    if row.prompt_render_log_json:
        try:
            render_log = json.loads(row.prompt_render_log_json)
        except json.JSONDecodeError:
            render_log = {"_raw": row.prompt_render_log_json}
    payload = GenerationRunOut(
        id=row.id,
        project_id=row.project_id,
        actor_user_id=row.actor_user_id,
        chapter_id=row.chapter_id,
        type=row.type,
        provider=row.provider,
        model=row.model,
        request_id=row.request_id,
        prompt_system=redact_text(row.prompt_system) if row.prompt_system else None,
        prompt_user=redact_text(row.prompt_user) if row.prompt_user else None,
        prompt_render_log=render_log,
        params=params,
        output_text=row.output_text,
        error=err,
        created_at=row.created_at,
    ).model_dump()
    return ok_payload(request_id=request_id, data={"run": payload})


@router.get("/generation_runs/{run_id}/debug_bundle")
def download_debug_bundle(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    run_id: str,
    include_prompt_inspector: str | None = Query(default="0"),
) -> Response:
    request_id = request.state.request_id
    row = require_generation_run_viewer(db, run_id=run_id, user_id=user_id)

    params = _safe_json_dict(row.params_json)
    if not _as_bool(include_prompt_inspector, False):
        params.pop("prompt_inspector", None)
    render_log = _safe_json_dict_or_none(row.prompt_render_log_json)
    err = _safe_json_dict_or_none(row.error_json)

    memory_log = params.get("memory_retrieval_log_json") if isinstance(params.get("memory_retrieval_log_json"), dict) else {}
    injection_cfg = params.get("memory_injection_config") if isinstance(params.get("memory_injection_config"), dict) else {}
    modules = injection_cfg.get("modules") if isinstance(injection_cfg.get("modules"), dict) else {}
    normalized_query_text = str(injection_cfg.get("normalized_query_text") or injection_cfg.get("query_text") or "").strip()

    sources: list[VectorSource] = ["worldbook", "outline", "chapter"]
    settings_row = db.get(ProjectSettings, str(row.project_id))
    embedding = vector_embedding_overrides(settings_row)
    rerank = _vector_rerank_config(settings_row)

    vector_rag_enabled = bool(modules.get("vector_rag", True))
    try:
        if vector_rag_enabled and normalized_query_text:
            vector_rag = query_project(
                project_id=str(row.project_id),
                query_text=normalized_query_text,
                sources=sources,
                embedding=embedding,
                rerank=rerank,
            )
        else:
            vector_rag = vector_rag_status(
                project_id=str(row.project_id),
                sources=sources,
                embedding=embedding,
                rerank=rerank,
            )
            if not vector_rag_enabled:
                vector_rag["enabled"] = False
                vector_rag["disabled_reason"] = "disabled"
            vector_rag["query_text"] = normalized_query_text
    except Exception as exc:
        vector_rag = vector_rag_status(
            project_id=str(row.project_id),
            sources=sources,
            embedding=embedding,
            rerank=rerank,
        )
        vector_rag["enabled"] = False
        vector_rag["disabled_reason"] = "error"
        vector_rag["query_text"] = normalized_query_text
        vector_rag["error"] = f"debug_bundle_vector_query_failed:{type(exc).__name__}"

    bundle = {
        "schema_version": "debug_bundle_v1",
        "request_id": request_id,
        "run": {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "chapter_id": str(row.chapter_id) if row.chapter_id else None,
            "type": str(row.type),
            "provider": str(row.provider) if row.provider else None,
            "model": str(row.model) if row.model else None,
            "run_request_id": str(row.request_id) if row.request_id else None,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
        },
        "prompt": {
            "system": redact_text(str(row.prompt_system or "")),
            "user": redact_text(str(row.prompt_user or "")),
            "render_log": render_log,
        },
        "params": params,
        "memory_retrieval_log": memory_log,
        "vector_rag": vector_rag,
        "memory_injection": {
            "normalized_query_text": normalized_query_text,
            "modules": modules,
        },
        "error": err,
    }

    safe_bundle = redact_api_keys(bundle)
    payload = json.dumps(safe_bundle, ensure_ascii=False, indent=2) + "\n"

    filename = f"debug_bundle_{row.id}.json"
    return Response(
        content=payload.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
