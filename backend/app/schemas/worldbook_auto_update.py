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

    @model_validator(mode="before")
    @classmethod
    def _normalize_item_shape(cls, data: Any) -> Any:
        """
        Compatibility: some models output {"item": {...}} with {"content": "...", "priority": 10}.
        Normalize to {"entry": {"content_md": "...", "priority": "must"}} and drop unknown fields.
        """
        if not isinstance(data, dict):
            return data

        def _priority_to_string(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                v = value.strip().lower()
                if v in {"drop_first", "optional", "important", "must"}:
                    return v
                try:
                    n = float(v)
                except Exception:
                    return None
                value = n
            if isinstance(value, (int, float)):
                n = float(value)
                if n <= 0:
                    return "drop_first"
                if n < 2:
                    return "optional"
                if n < 6:
                    return "important"
                return "must"
            return None

        obj = dict(data)

        item = obj.get("item")
        if isinstance(item, dict) and obj.get("entry") is None:
            entry: dict[str, Any] = {}

            title = item.get("title")
            if isinstance(title, str) and title.strip():
                entry["title"] = title.strip()

            content_md: str | None = None
            if isinstance(item.get("content_md"), str) and str(item.get("content_md") or "").strip():
                content_md = str(item.get("content_md") or "").strip()
            elif isinstance(item.get("content"), str) and str(item.get("content") or "").strip():
                content_md = str(item.get("content") or "").strip()
            elif isinstance(item.get("description"), str) and str(item.get("description") or "").strip():
                content_md = str(item.get("description") or "").strip()
            if content_md is not None:
                entry["content_md"] = content_md

            keywords = item.get("keywords")
            if isinstance(keywords, list):
                entry["keywords"] = [str(s).strip() for s in keywords if isinstance(s, str) and s.strip()]

            aliases = item.get("aliases")
            if isinstance(aliases, list):
                entry["aliases"] = [str(s).strip() for s in aliases if isinstance(s, str) and s.strip()]

            for k in ("enabled", "constant", "exclude_recursion", "prevent_recursion"):
                v = item.get(k)
                if isinstance(v, bool):
                    entry[k] = v

            char_limit = item.get("char_limit")
            if isinstance(char_limit, int):
                entry["char_limit"] = int(char_limit)

            priority = _priority_to_string(item.get("priority"))
            if priority is not None:
                entry["priority"] = priority

            obj["entry"] = entry
            obj.pop("item", None)

        entry2 = obj.get("entry")
        if isinstance(entry2, dict):
            entry_copy = dict(entry2)
            if "content_md" not in entry_copy and isinstance(entry_copy.get("content"), str):
                entry_copy["content_md"] = str(entry_copy.get("content") or "").strip()
                entry_copy.pop("content", None)

            priority2 = _priority_to_string(entry_copy.get("priority"))
            if priority2 is not None:
                entry_copy["priority"] = priority2

            allowed_entry_keys = {
                "title",
                "content_md",
                "keywords",
                "aliases",
                "enabled",
                "constant",
                "exclude_recursion",
                "prevent_recursion",
                "char_limit",
                "priority",
            }
            obj["entry"] = {k: v for k, v in entry_copy.items() if k in allowed_entry_keys}

        allowed_op_keys = {
            "op",
            "match_title",
            "entry",
            "merge_mode",
            "canonical_title",
            "duplicate_titles",
            "reason",
        }
        obj = {k: v for k, v in obj.items() if k in allowed_op_keys}
        return obj

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
    # Fail-soft: allow ops missing/empty as no-op.
    ops: list[WorldbookAutoUpdateOpV1] = Field(default_factory=list, max_length=MAX_OPS_V1)
