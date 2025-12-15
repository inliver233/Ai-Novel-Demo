from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.llm import LLMProvider


class LLMPresetOut(BaseModel):
    project_id: str
    provider: LLMProvider
    base_url: str | None = None
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    top_k: int | None = None
    stop: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMPresetPutRequest(BaseModel):
    provider: LLMProvider
    base_url: str | None = None
    model: str = Field(min_length=1, max_length=255)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    top_k: int | None = None
    stop: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = Field(default=None, ge=1, le=1800)
    extra: dict[str, Any] = Field(default_factory=dict)
