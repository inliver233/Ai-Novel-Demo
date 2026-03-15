from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.api.deps import UserIdDep
from app.core.errors import ok_payload
from app.schemas.llm_test import LLMTestRequest
from app.services.llm_test_app_service import llm_test as llm_test_service

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
    data = llm_test_service(
        user_id=user_id,
        body=body,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    return ok_payload(request_id=request_id, data=data)
