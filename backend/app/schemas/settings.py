from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.limits import MAX_TEXT_CHARS


class ProjectSettingsOut(BaseModel):
    project_id: str
    world_setting: str
    style_guide: str
    constraints: str


class ProjectSettingsUpdate(BaseModel):
    world_setting: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    style_guide: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    constraints: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
