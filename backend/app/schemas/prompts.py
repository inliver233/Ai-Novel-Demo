from __future__ import annotations

from pydantic import BaseModel, Field


class PromptTemplateItem(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    system_template: str | None = None
    user_template: str | None = None
    updated_at: str | None = None


class PromptsPutRequest(BaseModel):
    templates: list[PromptTemplateItem] = Field(min_length=1)

