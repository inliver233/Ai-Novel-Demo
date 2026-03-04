from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import RequestModel
from app.schemas.limits import MAX_JSON_CHARS_SMALL, validate_json_chars


def _validate_stop_items(value: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in value or []:
        if not isinstance(item, str):
            raise ValueError("stop must be strings")
        s = item.strip()
        if not s:
            raise ValueError("stop cannot contain empty strings")
        if len(s) > 256:
            raise ValueError("stop item too long")
        out.append(s)
    return out


class LLMProfileCreate(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str = Field(min_length=1, max_length=255)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    top_k: int | None = None
    stop: list[str] = Field(default_factory=list, max_length=32)
    timeout_seconds: int | None = Field(default=None, ge=1, le=1800)
    extra: dict[str, Any] = Field(default_factory=dict, max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)

    @field_validator("stop")
    @classmethod
    def _validate_stop(cls, v: list[str]) -> list[str]:
        return _validate_stop_items(v)

    @field_validator("extra")
    @classmethod
    def _validate_extra(cls, v: dict[str, Any]) -> dict[str, Any]:
        for k in (v or {}).keys():
            if not isinstance(k, str):
                raise ValueError("extra keys must be strings")
            if len(k) > 128:
                raise ValueError("extra key too long")
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_SMALL, field_name="extra") or {}


class LLMProfileUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider: str | None = Field(default=None, min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    top_k: int | None = None
    stop: list[str] | None = Field(default=None, max_length=32)
    timeout_seconds: int | None = Field(default=None, ge=1, le=1800)
    extra: dict[str, Any] | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)

    @field_validator("stop")
    @classmethod
    def _validate_stop(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _validate_stop_items(v)

    @field_validator("extra")
    @classmethod
    def _validate_extra(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        for k in v.keys():
            if not isinstance(k, str):
                raise ValueError("extra keys must be strings")
            if len(k) > 128:
                raise ValueError("extra key too long")
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_SMALL, field_name="extra") or {}


class LLMProfileOut(BaseModel):
    id: str
    owner_user_id: str
    name: str
    provider: str
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
    has_api_key: bool
    masked_api_key: str | None = None
    created_at: datetime
    updated_at: datetime
