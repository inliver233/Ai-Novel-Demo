from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MemoryUpdateSchemaVersion = Literal["memory_update_v1"]
MemoryTargetTable = Literal["entities", "relations", "events", "foreshadows", "evidence"]
MemoryOpType = Literal["upsert", "delete"]

MAX_OPS_V1 = 50
MAX_EVIDENCE_IDS_PER_OP = 20

MAX_ATTRIBUTES_JSON_CHARS = 8000
MAX_MD_CHARS = 40000


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _validate_attributes_size(attributes: dict[str, Any] | None) -> dict[str, Any] | None:
    if attributes is None:
        return None
    raw = _compact_json_dumps(attributes)
    if len(raw) > MAX_ATTRIBUTES_JSON_CHARS:
        raise ValueError(f"attributes too large ({len(raw)} chars)")
    return attributes


class _AfterBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityAfter(_AfterBase):
    entity_type: str = Field(default="generic", max_length=64)
    name: str = Field(min_length=1, max_length=255)
    summary_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)
    attributes: dict[str, Any] | None = None

    @field_validator("attributes")
    @classmethod
    def _validate_attributes(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_attributes_size(v)


class RelationAfter(_AfterBase):
    from_entity_id: str = Field(min_length=1, max_length=36)
    to_entity_id: str = Field(min_length=1, max_length=36)
    relation_type: str = Field(default="related_to", max_length=64)
    description_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)
    attributes: dict[str, Any] | None = None

    @field_validator("attributes")
    @classmethod
    def _validate_attributes(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_attributes_size(v)


class EventAfter(_AfterBase):
    chapter_id: str | None = Field(default=None, max_length=36)
    event_type: str = Field(default="event", max_length=64)
    title: str | None = Field(default=None, max_length=255)
    content_md: str = Field(default="", max_length=MAX_MD_CHARS)
    attributes: dict[str, Any] | None = None

    @field_validator("attributes")
    @classmethod
    def _validate_attributes(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_attributes_size(v)


class ForeshadowAfter(_AfterBase):
    chapter_id: str | None = Field(default=None, max_length=36)
    resolved_at_chapter_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, max_length=255)
    content_md: str = Field(default="", max_length=MAX_MD_CHARS)
    resolved: int = Field(default=0, ge=0, le=1)
    attributes: dict[str, Any] | None = None

    @field_validator("attributes")
    @classmethod
    def _validate_attributes(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_attributes_size(v)


class EvidenceAfter(_AfterBase):
    source_type: str = Field(default="unknown", max_length=32)
    source_id: str | None = Field(default=None, max_length=64)
    quote_md: str = Field(default="", max_length=MAX_MD_CHARS)
    attributes: dict[str, Any] | None = None

    @field_validator("attributes")
    @classmethod
    def _validate_attributes(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_attributes_size(v)


AFTER_MODEL_BY_TABLE: dict[str, type[_AfterBase]] = {
    "entities": EntityAfter,
    "relations": RelationAfter,
    "events": EventAfter,
    "foreshadows": ForeshadowAfter,
    "evidence": EvidenceAfter,
}


class MemoryUpdateOpV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: MemoryOpType
    target_table: MemoryTargetTable
    target_id: str | None = Field(default=None, max_length=64)
    after: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS_PER_OP)

    @field_validator("evidence_ids")
    @classmethod
    def _validate_evidence_ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("evidence_ids must be strings")
            item = item.strip()
            if not item:
                raise ValueError("evidence_ids cannot contain empty strings")
            if len(item) > 64:
                raise ValueError("evidence_id too long")
            out.append(item)
        return out

    @model_validator(mode="after")
    def _validate_op(self) -> "MemoryUpdateOpV1":
        if self.op == "delete":
            if not (self.target_id or "").strip():
                raise ValueError("target_id is required for delete")
            if self.after is not None:
                raise ValueError("after must be null for delete")
            return self

        if self.after is None:
            raise ValueError("after is required for upsert")

        model_cls = AFTER_MODEL_BY_TABLE.get(self.target_table)
        if model_cls is None:
            raise ValueError("unsupported target_table")
        model_cls.model_validate(self.after)
        return self


class MemoryUpdateV1Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: MemoryUpdateSchemaVersion = "memory_update_v1"
    idempotency_key: str = Field(min_length=8, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    summary_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)
    # Fail-soft: allow empty ops for no-op updates (contract parser may return ops_empty/ops_missing warnings).
    ops: list[MemoryUpdateOpV1] = Field(default_factory=list, max_length=MAX_OPS_V1)
