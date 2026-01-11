from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import ORMModel, RequestModel


class ProjectCreate(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    genre: str | None = Field(default=None, max_length=255)
    logline: str | None = Field(default=None, max_length=1024)


class ProjectUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    genre: str | None = Field(default=None, max_length=255)
    logline: str | None = Field(default=None, max_length=1024)
    active_outline_id: str | None = Field(default=None, max_length=36)
    llm_profile_id: str | None = Field(default=None, max_length=36)


class ProjectOut(ORMModel):
    id: str
    owner_user_id: str
    active_outline_id: str | None = None
    llm_profile_id: str | None = None
    name: str
    genre: str | None = None
    logline: str | None = None
    created_at: datetime
    updated_at: datetime
