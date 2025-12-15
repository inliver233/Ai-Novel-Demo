from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OutlineGenerateContext(BaseModel):
    include_world_setting: bool = True
    include_characters: bool = True


class OutlineGenerateRequest(BaseModel):
    requirements: dict[str, Any] = Field(default_factory=dict)
    context: OutlineGenerateContext = Field(default_factory=OutlineGenerateContext)

