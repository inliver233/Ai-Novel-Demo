from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import RequestModel


class WritingStyleOut(BaseModel):
    id: str
    owner_user_id: str | None = None
    name: str
    description: str | None = None
    prompt_content: str
    is_preset: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WritingStyleCreateRequest(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    prompt_content: str = Field(min_length=1, max_length=8000)


class WritingStyleUpdateRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    prompt_content: str | None = Field(default=None, min_length=1, max_length=8000)


class ProjectDefaultStyleOut(BaseModel):
    project_id: str
    style_id: str | None = None
    updated_at: datetime | None = None


class ProjectDefaultStylePutRequest(RequestModel):
    style_id: str | None = None
