from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.limits import MAX_JSON_CHARS_SMALL, validate_json_chars


class OutlineGenerateContext(BaseModel):
    include_world_setting: bool = True
    include_characters: bool = True


class OutlineGenerateRequest(BaseModel):
    requirements: dict[str, Any] = Field(default_factory=dict, max_length=200)
    style_id: str | None = Field(default=None, max_length=36)
    context: OutlineGenerateContext = Field(default_factory=OutlineGenerateContext)

    @field_validator("requirements")
    @classmethod
    def _validate_requirements(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_SMALL, field_name="requirements") or {}
