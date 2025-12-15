from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.llm import LLMProvider


class LLMTestRequest(BaseModel):
    provider: LLMProvider
    base_url: str | None = None
    model: str = Field(min_length=1, max_length=255)
    timeout_seconds: int | None = Field(default=90, ge=1, le=1800)
    params: dict[str, Any] = Field(default_factory=dict)
