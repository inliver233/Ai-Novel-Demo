from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_owned_llm_profile, require_project_editor
from app.core.errors import AppError, ok_payload
from app.llm.capabilities import max_context_tokens_limit, max_output_tokens_limit, recommended_max_tokens
from app.llm.utils import default_max_tokens, normalize_base_url
from app.models.llm_task_preset import LLMTaskPreset
from app.schemas.llm_task_presets import LLMTaskPresetOut, LLMTaskPresetPutRequest
from app.services.llm_task_catalog import LLM_TASK_CATALOG, is_supported_llm_task

router = APIRouter()


def _normalize_base_url_for_provider(provider: str, base_url: str | None) -> str | None:
    if provider in ("openai", "openai_responses"):
        return normalize_base_url(base_url or "https://api.openai.com/v1")
    if provider in ("openai_compatible", "openai_responses_compatible"):
        if not base_url:
            raise AppError(code="LLM_CONFIG_ERROR", message=f"{provider} 必须填写 base_url", status_code=400)
        return normalize_base_url(base_url)
    if provider == "anthropic":
        return normalize_base_url(base_url or "https://api.anthropic.com")
    if provider == "gemini":
        return normalize_base_url(base_url or "https://generativelanguage.googleapis.com")
    raise AppError(code="LLM_CONFIG_ERROR", message="不支持的 provider", status_code=400)


def _to_out(row: LLMTaskPreset) -> dict:
    stop: list[str] = []
    if row.stop_json:
        try:
            stop = json.loads(row.stop_json)
        except Exception:
            stop = []
    extra: dict = {}
    if row.extra_json:
        try:
            extra = json.loads(row.extra_json)
        except Exception:
            extra = {}

    max_tokens_limit = max_output_tokens_limit(row.provider, row.model)
    max_tokens_recommended = recommended_max_tokens(row.provider, row.model)
    context_window_limit = max_context_tokens_limit(row.provider, row.model)
    return LLMTaskPresetOut(
        project_id=row.project_id,
        task_key=row.task_key,
        llm_profile_id=row.llm_profile_id,
        provider=row.provider,  # type: ignore[arg-type]
        base_url=row.base_url,
        model=row.model,
        temperature=row.temperature,
        top_p=row.top_p,
        max_tokens=row.max_tokens,
        max_tokens_limit=max_tokens_limit,
        max_tokens_recommended=max_tokens_recommended,
        context_window_limit=context_window_limit,
        presence_penalty=row.presence_penalty,
        frequency_penalty=row.frequency_penalty,
        top_k=row.top_k,
        stop=stop or [],
        timeout_seconds=row.timeout_seconds,
        extra=extra or {},
        source="task_override",
    ).model_dump()


def _catalog_out() -> list[dict]:
    return [
        {
            "key": item.key,
            "label": item.label,
            "group": item.group,
            "description": item.description,
        }
        for item in LLM_TASK_CATALOG
    ]


@router.get("/projects/{project_id}/llm_task_presets")
def list_llm_task_presets(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    rows = (
        db.execute(select(LLMTaskPreset).where(LLMTaskPreset.project_id == project_id).order_by(LLMTaskPreset.task_key.asc()))
        .scalars()
        .all()
    )
    return ok_payload(
        request_id=request_id,
        data={
            "catalog": _catalog_out(),
            "task_presets": [_to_out(row) for row in rows],
        },
    )


@router.put("/projects/{project_id}/llm_task_presets/{task_key}")
def put_llm_task_preset(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    task_key: str,
    body: LLMTaskPresetPutRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    task_key_norm = str(task_key or "").strip()
    if not task_key_norm or not is_supported_llm_task(task_key_norm):
        raise AppError.validation(message=f"不支持的 task_key: {task_key_norm or '(empty)'}")

    profile_id = body.llm_profile_id
    if profile_id:
        profile = require_owned_llm_profile(db, profile_id=profile_id, user_id=user_id)
        if profile.provider != body.provider:
            raise AppError(
                code="LLM_CONFIG_ERROR",
                message="任务模块 provider 必须与所选 API 配置库 provider 一致",
                status_code=400,
            )

    base_url = _normalize_base_url_for_provider(body.provider, body.base_url)

    row = db.get(LLMTaskPreset, (project_id, task_key_norm))
    if row is None:
        row = LLMTaskPreset(project_id=project_id, task_key=task_key_norm, provider=body.provider, model=body.model)
        db.add(row)

    row.llm_profile_id = profile_id
    row.provider = body.provider
    row.base_url = base_url
    row.model = body.model
    row.temperature = body.temperature
    row.top_p = body.top_p
    if body.max_tokens is None:
        row.max_tokens = default_max_tokens(body.provider, body.model)
    else:
        max_tokens = int(body.max_tokens)
        if max_tokens <= 0:
            raise AppError.validation(message="最大 tokens（max_tokens）必须为正整数")
        limit = max_output_tokens_limit(body.provider, body.model)
        row.max_tokens = min(max_tokens, limit) if limit else max_tokens
    row.presence_penalty = body.presence_penalty
    row.frequency_penalty = body.frequency_penalty
    row.top_k = body.top_k
    row.stop_json = json.dumps(body.stop or [], ensure_ascii=False)
    row.timeout_seconds = body.timeout_seconds
    row.extra_json = json.dumps(body.extra or {}, ensure_ascii=False)

    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"task_preset": _to_out(row)})


@router.delete("/projects/{project_id}/llm_task_presets/{task_key}")
def delete_llm_task_preset(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, task_key: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    task_key_norm = str(task_key or "").strip()
    row = db.get(LLMTaskPreset, (project_id, task_key_norm))
    if row is None:
        raise AppError.not_found()
    db.delete(row)
    db.commit()
    return ok_payload(request_id=request_id, data={})
