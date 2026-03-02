from __future__ import annotations

import json

from fastapi import APIRouter, Request

from app.api.deps import DbDep, UserIdDep, require_project_editor
from app.core.errors import AppError, ok_payload
from app.llm.capabilities import max_context_tokens_limit, max_output_tokens_limit, recommended_max_tokens
from app.llm.utils import default_max_tokens, normalize_base_url
from app.models.llm_preset import LLMPreset
from app.schemas.llm_preset import LLMPresetOut, LLMPresetPutRequest

router = APIRouter()


def _default_preset(project_id: str) -> LLMPreset:
    return LLMPreset(
        project_id=project_id,
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.7,
        top_p=1.0,
        max_tokens=default_max_tokens("openai", "gpt-4o-mini"),
        presence_penalty=0.0,
        frequency_penalty=0.0,
        top_k=None,
        stop_json="[]",
        timeout_seconds=180,
        extra_json="{}",
    )


def _to_out(row: LLMPreset) -> dict:
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
    return LLMPresetOut(
        project_id=row.project_id,
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
    ).model_dump()


@router.get("/projects/{project_id}/llm_preset")
def get_llm_preset(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    row = db.get(LLMPreset, project_id)
    if row is None:
        row = _default_preset(project_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return ok_payload(request_id=request_id, data={"llm_preset": _to_out(row)})


@router.put("/projects/{project_id}/llm_preset")
def put_llm_preset(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: LLMPresetPutRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    base_url = body.base_url
    if body.provider in ("openai", "openai_responses"):
        base_url = normalize_base_url(base_url or "https://api.openai.com/v1")
    elif body.provider in ("openai_compatible", "openai_responses_compatible"):
        if not base_url:
            raise AppError(code="LLM_CONFIG_ERROR", message=f"{body.provider} 必须填写 base_url", status_code=400)
        base_url = normalize_base_url(base_url)
    elif body.provider == "anthropic":
        base_url = normalize_base_url(base_url or "https://api.anthropic.com")
    elif body.provider == "gemini":
        base_url = normalize_base_url(base_url or "https://generativelanguage.googleapis.com")

    row = db.get(LLMPreset, project_id)
    if row is None:
        row = _default_preset(project_id)
        db.add(row)

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
    return ok_payload(request_id=request_id, data={"llm_preset": _to_out(row)})
