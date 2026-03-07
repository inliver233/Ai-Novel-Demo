from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.errors import ok_payload
from app.schemas.llm import LLMProvider
from app.services.llm_contract_service import capability_contract

router = APIRouter()


@router.get("/llm_capabilities")
def get_llm_capabilities(request: Request, provider: LLMProvider, model: str) -> dict:
    request_id = request.state.request_id
    return ok_payload(
        request_id=request_id,
        data={
            "capabilities": capability_contract(provider, model),
        },
    )
