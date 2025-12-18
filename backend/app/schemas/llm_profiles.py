from __future__ import annotations

from pydantic import BaseModel, Field


class LLMProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str = Field(min_length=1, max_length=255)


class LLMProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider: str | None = Field(default=None, min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=255)


class LLMProfileOut(BaseModel):
    id: str
    owner_user_id: str
    name: str
    provider: str
    base_url: str | None = None
    model: str
    created_at: str
    updated_at: str
