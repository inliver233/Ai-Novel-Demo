from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import ORMModel
from app.schemas.limits import MAX_TEXT_CHARS


class CharacterCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    notes: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)


class CharacterUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    notes: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)


class CharacterOut(ORMModel):
    id: str
    project_id: str
    name: str
    role: str | None = None
    profile: str | None = None
    notes: str | None = None
    updated_at: datetime
