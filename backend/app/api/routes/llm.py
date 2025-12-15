from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.core.errors import AppError, ok_payload
from app.llm.client import call_llm
from app.schemas.llm_test import LLMTestRequest

router = APIRouter()


@router.post("/llm/test")
def llm_test(
    request: Request,
    body: LLMTestRequest,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key"),
) -> dict:
    request_id = request.state.request_id
    if not x_llm_provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="缺少 X-LLM-Provider", status_code=400)
    if x_llm_provider != body.provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="Header X-LLM-Provider 必须与 body.provider 一致", status_code=400)
    if not x_llm_api_key:
        raise AppError(code="LLM_KEY_MISSING", message="请先填写 API Key", status_code=401)

    base_url = body.base_url
    if body.provider == "openai":
        base_url = base_url or "https://api.openai.com/v1"
    elif body.provider == "anthropic":
        base_url = base_url or "https://api.anthropic.com"
    elif body.provider == "gemini":
        base_url = base_url or "https://generativelanguage.googleapis.com"
    elif body.provider == "openai_compatible" and not base_url:
        raise AppError(code="LLM_CONFIG_ERROR", message="openai_compatible 必须填写 base_url", status_code=400)

    params = dict(body.params or {})
    params.setdefault("max_tokens", 8)
    params.setdefault("temperature", 0)

    result = call_llm(
        provider=body.provider,
        base_url=str(base_url),
        model=body.model,
        api_key=str(x_llm_api_key),
        system="You are a connection test.",
        user="Reply with 'pong' only.",
        params=params,
        timeout_seconds=int(body.timeout_seconds or 90),
        extra={},
    )

    return ok_payload(request_id=request_id, data={"latency_ms": result.latency_ms})
