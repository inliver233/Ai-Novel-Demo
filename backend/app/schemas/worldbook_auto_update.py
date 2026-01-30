from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WorldbookAutoUpdateSchemaVersion = Literal["worldbook_auto_update_v1"]
WorldbookAutoUpdateOpType = Literal["create", "update", "merge", "dedupe"]
WorldbookMergeMode = Literal["append_missing", "append", "replace"]

MAX_OPS_V1 = 80
MAX_KEYWORDS_V1 = 40
MAX_ALIASES_V1 = 40
MAX_MD_CHARS_V1 = 40000


class WorldbookEntryPatchV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    content_md: str | None = Field(default=None, max_length=MAX_MD_CHARS_V1)
    keywords: list[str] | None = Field(default=None, max_length=MAX_KEYWORDS_V1)
    aliases: list[str] | None = Field(default=None, max_length=MAX_ALIASES_V1)

    enabled: bool | None = None
    constant: bool | None = None
    exclude_recursion: bool | None = None
    prevent_recursion: bool | None = None
    char_limit: int | None = Field(default=None, ge=0, le=20000)
    priority: str | None = Field(default=None, max_length=32)


class WorldbookEntryCreateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    content_md: str = Field(default="", max_length=MAX_MD_CHARS_V1)
    keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS_V1)
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES_V1)

    enabled: bool = True
    constant: bool = False
    exclude_recursion: bool = False
    prevent_recursion: bool = False
    char_limit: int = Field(default=12000, ge=0, le=20000)
    priority: str = Field(default="important", max_length=32)


class WorldbookAutoUpdateOpV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: WorldbookAutoUpdateOpType

    # For update/merge: how to locate the existing entry (service layer should match by title/alias).
    match_title: str | None = Field(default=None, max_length=255)

    # For create/update/merge.
    entry: dict[str, Any] | None = None

    # For merge ops only (how to combine new info with existing).
    merge_mode: WorldbookMergeMode | None = None

    # For dedupe ops.
    canonical_title: str | None = Field(default=None, max_length=255)
    duplicate_titles: list[str] = Field(default_factory=list, max_length=50)

    reason: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def _validate_op(self) -> "WorldbookAutoUpdateOpV1":
        if self.op == "dedupe":
            if not (self.canonical_title or "").strip():
                raise ValueError("canonical_title is required for dedupe")
            if not self.duplicate_titles:
                raise ValueError("duplicate_titles is required for dedupe")
            return self

        if self.op == "create":
            if self.entry is None:
                raise ValueError("entry is required for create")
            WorldbookEntryCreateV1.model_validate(self.entry)
            return self

        if self.op in {"update", "merge"}:
            if not (self.match_title or "").strip():
                raise ValueError("match_title is required for update/merge")
            if self.entry is None:
                raise ValueError("entry is required for update/merge")
            WorldbookEntryPatchV1.model_validate(self.entry)
            if self.op == "merge" and not (self.merge_mode or "").strip():
                raise ValueError("merge_mode is required for merge")
            return self

        raise ValueError("unsupported op")


class WorldbookAutoUpdateV1Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: WorldbookAutoUpdateSchemaVersion = "worldbook_auto_update_v1"
    title: str | None = Field(default=None, max_length=255)
    summary_md: str | None = Field(default=None, max_length=MAX_MD_CHARS_V1)
    ops: list[WorldbookAutoUpdateOpV1] = Field(min_length=1, max_length=MAX_OPS_V1)
