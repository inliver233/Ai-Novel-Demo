from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.limits import MAX_TEXT_CHARS


class QueryPreprocessingConfig(BaseModel):
    enabled: bool = False
    tags: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    index_ref_enhance: bool = False


class ProjectSettingsOut(BaseModel):
    project_id: str
    world_setting: str
    style_guide: str
    constraints: str
    vector_embedding_base_url: str
    vector_embedding_model: str
    vector_embedding_has_api_key: bool
    vector_embedding_masked_api_key: str
    vector_embedding_effective_base_url: str
    vector_embedding_effective_model: str
    vector_embedding_effective_has_api_key: bool
    vector_embedding_effective_masked_api_key: str
    vector_embedding_effective_disabled_reason: str | None = None
    vector_embedding_effective_source: str


class ProjectSettingsUpdate(BaseModel):
    world_setting: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    style_guide: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    constraints: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    vector_embedding_base_url: str | None = Field(default=None, max_length=2048)
    vector_embedding_model: str | None = Field(default=None, max_length=255)
    vector_embedding_api_key: str | None = Field(default=None, max_length=2048)
