from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.llm import LLMProvider
from app.schemas.limits import MAX_JSON_CHARS_SMALL, validate_json_chars


class LLMTestRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=36)
    profile_id: str | None = Field(default=None, max_length=36)
    provider: LLMProvider
    base_url: str | None = Field(default=None, max_length=2048)
    model: str = Field(min_length=1, max_length=255)
    timeout_seconds: int | None = Field(default=180, ge=1, le=1800)
    params: dict[str, Any] = Field(default_factory=dict, max_length=200)
    extra: dict[str, Any] = Field(default_factory=dict, max_length=200)

    @field_validator("params")
    @classmethod
    def _validate_params(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_SMALL, field_name="params") or {}

    @field_validator("extra")
    @classmethod
    def _validate_extra(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_SMALL, field_name="extra") or {}
