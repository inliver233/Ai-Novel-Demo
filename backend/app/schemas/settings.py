from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.limits import MAX_TEXT_CHARS


class QueryPreprocessingConfig(BaseModel):
    enabled: bool = False
    tags: list[str] = Field(default_factory=list, max_length=50)
    exclusion_rules: list[str] = Field(default_factory=list, max_length=50)
    index_ref_enhance: bool = False

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("tags must be strings")
            item = item.strip()
            if not item:
                raise ValueError("tags cannot contain empty strings")
            if len(item) > 64:
                raise ValueError("tag too long")
            out.append(item)
        return out

    @field_validator("exclusion_rules")
    @classmethod
    def _validate_exclusion_rules(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("exclusion_rules must be strings")
            item = item.strip()
            if not item:
                raise ValueError("exclusion_rules cannot contain empty strings")
            if len(item) > 256:
                raise ValueError("exclusion_rule too long")
            out.append(item)
        return out


class ProjectSettingsOut(BaseModel):
    project_id: str
    world_setting: str
    style_guide: str
    constraints: str

    query_preprocessing: QueryPreprocessingConfig | None
    query_preprocessing_default: QueryPreprocessingConfig
    query_preprocessing_effective: QueryPreprocessingConfig
    query_preprocessing_effective_source: str

    vector_rerank_enabled: bool | None
    vector_rerank_method: str | None
    vector_rerank_top_k: int | None
    vector_rerank_effective_enabled: bool
    vector_rerank_effective_method: str
    vector_rerank_effective_top_k: int
    vector_rerank_effective_source: str

    vector_embedding_provider: str
    vector_embedding_base_url: str
    vector_embedding_model: str
    vector_embedding_azure_deployment: str
    vector_embedding_azure_api_version: str
    vector_embedding_sentence_transformers_model: str
    vector_embedding_has_api_key: bool
    vector_embedding_masked_api_key: str
    vector_embedding_effective_provider: str
    vector_embedding_effective_base_url: str
    vector_embedding_effective_model: str
    vector_embedding_effective_azure_deployment: str
    vector_embedding_effective_azure_api_version: str
    vector_embedding_effective_sentence_transformers_model: str
    vector_embedding_effective_has_api_key: bool
    vector_embedding_effective_masked_api_key: str
    vector_embedding_effective_disabled_reason: str | None = None
    vector_embedding_effective_source: str


class ProjectSettingsUpdate(BaseModel):
    world_setting: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    style_guide: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    constraints: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)

    query_preprocessing: QueryPreprocessingConfig | None = None

    vector_rerank_enabled: bool | None = None
    vector_rerank_method: str | None = Field(default=None, max_length=64)
    vector_rerank_top_k: int | None = Field(default=None, ge=1, le=1000)

    vector_embedding_provider: str | None = Field(default=None, max_length=64)
    vector_embedding_base_url: str | None = Field(default=None, max_length=2048)
    vector_embedding_model: str | None = Field(default=None, max_length=255)
    vector_embedding_azure_deployment: str | None = Field(default=None, max_length=255)
    vector_embedding_azure_api_version: str | None = Field(default=None, max_length=64)
    vector_embedding_sentence_transformers_model: str | None = Field(default=None, max_length=255)
    vector_embedding_api_key: str | None = Field(default=None, max_length=2048)
