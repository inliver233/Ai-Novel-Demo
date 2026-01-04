from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.errors import ok_payload
from app.llm.capabilities import max_context_tokens_limit, max_output_tokens_limit, recommended_max_tokens
from app.schemas.llm import LLMProvider

router = APIRouter()


@router.get("/llm_capabilities")
def get_llm_capabilities(request: Request, provider: LLMProvider, model: str) -> dict:
    request_id = request.state.request_id
    return ok_payload(
        request_id=request_id,
        data={
            "capabilities": {
                "provider": provider,
                "model": model,
                "max_tokens_limit": max_output_tokens_limit(provider, model),
                "max_tokens_recommended": recommended_max_tokens(provider, model),
                "context_window_limit": max_context_tokens_limit(provider, model),
            }
        },
    )

