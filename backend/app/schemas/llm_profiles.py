from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import RequestModel


class LLMProfileCreate(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str = Field(min_length=1, max_length=255)
    api_key: str | None = Field(default=None, max_length=4096)


class LLMProfileUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider: str | None = Field(default=None, min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    api_key: str | None = Field(default=None, max_length=4096)


class LLMProfileOut(BaseModel):
    id: str
    owner_user_id: str
    name: str
    provider: str
    base_url: str | None = None
    model: str
    has_api_key: bool
    masked_api_key: str | None = None
    created_at: datetime
    updated_at: datetime
