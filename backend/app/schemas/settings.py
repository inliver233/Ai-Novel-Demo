from __future__ import annotations

from pydantic import BaseModel


class ProjectSettingsOut(BaseModel):
    project_id: str
    world_setting: str
    style_guide: str
    constraints: str


class ProjectSettingsUpdate(BaseModel):
    world_setting: str | None = None
    style_guide: str | None = None
    constraints: str | None = None

