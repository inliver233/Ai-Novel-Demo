from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import ORMModel


class CharacterCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    profile: str | None = None
    notes: str | None = None


class CharacterUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    profile: str | None = None
    notes: str | None = None


class CharacterOut(ORMModel):
    id: str
    project_id: str
    name: str
    role: str | None = None
    profile: str | None = None
    notes: str | None = None
    updated_at: datetime
