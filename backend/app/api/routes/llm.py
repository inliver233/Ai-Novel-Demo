from __future__ import annotations

import time

from fastapi import APIRouter, Header, Request

from app.api.deps import UserIdDep, require_owned_llm_profile, require_project_editor
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.llm.client import call_llm
from app.schemas.llm_test import LLMTestRequest
from app.services.llm_key_resolver import normalize_header_api_key, resolve_api_key
from app.services.llm_retry import (
    compute_backoff_seconds,
    is_retryable_llm_error,
    task_llm_max_attempts,
    task_llm_retry_base_seconds,
    task_llm_retry_jitter,
    task_llm_retry_max_seconds,
)

router = APIRouter()


@router.post("/llm/test")
def llm_test(
    request: Request,
    user_id: UserIdDep,
    body: LLMTestRequest,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    if x_llm_provider and x_llm_provider != body.provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="请求头 X-LLM-Provider 必须与 body.provider 一致", status_code=400)

    header_key = normalize_header_api_key(x_llm_api_key)
    if header_key is not None:
        resolved_api_key = header_key
    else:
        db = SessionLocal()
        try:
            project = require_project_editor(db, project_id=body.project_id, user_id=user_id) if body.project_id else None
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

    max_attempts = task_llm_max_attempts(default=2)
    attempts: list[dict] = []
    result = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = call_llm(
                provider=body.provider,
                base_url=str(base_url),
                model=body.model,
                api_key=str(resolved_api_key),
                system="You are a connection test.",
                user="Reply with 'pong' only.",
                params=params,
                timeout_seconds=int(body.timeout_seconds or 180),
                extra=dict(body.extra or {}),
            )
            break
        except AppError as exc:
            retryable = is_retryable_llm_error(exc)
            attempts.append(
                {
                    "attempt": int(attempt),
                    "error_code": str(exc.code),
                    "status_code": int(exc.status_code),
                    "retryable": bool(retryable),
                }
            )
            if attempt >= max_attempts or not retryable:
                if attempts:
                    exc.details = {**(exc.details or {}), "attempts": attempts, "attempt_max": int(max_attempts)}
                raise

            delay = compute_backoff_seconds(
                attempt=attempt + 1,
                base_seconds=task_llm_retry_base_seconds(),
                max_seconds=task_llm_retry_max_seconds(),
                jitter=task_llm_retry_jitter(),
                error_code=str(exc.code),
            )
            attempts[-1]["sleep_seconds"] = float(delay)
            if delay > 0:
                time.sleep(float(delay))

    if result is None:
        raise AppError(code="LLM_UPSTREAM_ERROR", message="模型服务异常，请稍后重试", status_code=502)

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
