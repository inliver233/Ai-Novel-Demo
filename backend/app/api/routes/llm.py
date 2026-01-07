from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.api.deps import UserIdDep, require_owned_llm_profile, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.llm.client import call_llm
from app.schemas.llm_test import LLMTestRequest
from app.services.llm_key_resolver import normalize_header_api_key, resolve_api_key

router = APIRouter()


@router.post("/llm/test")
def llm_test(
    request: Request,
    user_id: UserIdDep,
    body: LLMTestRequest,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key"),
) -> dict:
    request_id = request.state.request_id
    if x_llm_provider and x_llm_provider != body.provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="Header X-LLM-Provider 必须与 body.provider 一致", status_code=400)

    header_key = normalize_header_api_key(x_llm_api_key)
    if header_key is not None:
        resolved_api_key = header_key
    else:
        db = SessionLocal()
        try:
            project = require_owned_project(db, project_id=body.project_id, user_id=user_id) if body.project_id else None
            profile_id = (body.profile_id or "").strip() or (project.llm_profile_id if project is not None else None)
            profile = require_owned_llm_profile(db, profile_id=profile_id, user_id=user_id) if profile_id else None
            if profile is not None and profile.provider != body.provider:
                raise AppError(code="LLM_CONFIG_ERROR", message="当前配置 provider 与请求不一致", status_code=400)
            resolved_api_key = resolve_api_key(db, user_id=user_id, header_api_key=None, project=project, profile=profile)
        finally:
            db.close()

    base_url = body.base_url
    if body.provider in ("openai", "openai_responses"):
        base_url = base_url or "https://api.openai.com/v1"
    elif body.provider == "anthropic":
        base_url = base_url or "https://api.anthropic.com"
    elif body.provider == "gemini":
        base_url = base_url or "https://generativelanguage.googleapis.com"
    elif body.provider in ("openai_compatible", "openai_responses_compatible") and not base_url:
        raise AppError(code="LLM_CONFIG_ERROR", message=f"{body.provider} 必须填写 base_url", status_code=400)

    params = dict(body.params or {})
    # Some providers/models may emit "thinking" blocks before the final text output; keep this > tiny so we can
    # reliably parse a small text preview for connection tests.
    params.setdefault("max_tokens", 64)
    params.setdefault("temperature", 0)

    result = call_llm(
        provider=body.provider,
        base_url=str(base_url),
        model=body.model,
        api_key=str(resolved_api_key),
        system="You are a connection test.",
        user="Reply with 'pong' only.",
        params=params,
        timeout_seconds=int(body.timeout_seconds or 90),
        extra=dict(body.extra or {}),
    )

    text_preview = (result.text or "").strip()
    if len(text_preview) > 200:
        text_preview = text_preview[:200]
    return ok_payload(
        request_id=request_id,
        data={
            "latency_ms": result.latency_ms,
            "text": text_preview,
            "finish_reason": result.finish_reason,
            "dropped_params": result.dropped_params,
        },
    )
