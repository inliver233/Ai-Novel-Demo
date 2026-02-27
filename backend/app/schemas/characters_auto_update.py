from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CharactersAutoUpdateSchemaVersion = Literal["characters_auto_update_v1"]
CharactersAutoUpdateOpType = Literal["upsert", "dedupe"]
CharacterMergeMode = Literal["append_missing", "append", "replace"]

MAX_OPS_V1 = 80
MAX_MD_CHARS_V1 = 20000


class CharacterPatchV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=MAX_MD_CHARS_V1)
    notes: str | None = Field(default=None, max_length=MAX_MD_CHARS_V1)


class CharactersAutoUpdateOpV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: CharactersAutoUpdateOpType

    # For upsert.
    name: str | None = Field(default=None, max_length=255)
    patch: dict[str, Any] | None = None
    merge_mode_profile: CharacterMergeMode | None = None
    merge_mode_notes: CharacterMergeMode | None = None

    # For dedupe.
    canonical_name: str | None = Field(default=None, max_length=255)
    duplicate_names: list[str] = Field(default_factory=list, max_length=50)

    reason: str | None = Field(default=None, max_length=400)

    @model_validator(mode="before")
    @classmethod
    def _normalize_character_shape(cls, data: Any) -> Any:
        """
        Compatibility: some models output {"character": {...}} for upsert ops.
        Normalize to name + patch and drop unknown fields.
        """
        if not isinstance(data, dict):
            return data

        obj = dict(data)
        character = obj.get("character")
        if isinstance(character, dict):
            # name
            name = obj.get("name")
            if not (isinstance(name, str) and name.strip()):
                cname = character.get("name")
                if isinstance(cname, str) and cname.strip():
                    obj["name"] = cname.strip()

            # patch
            patch_in = obj.get("patch") if isinstance(obj.get("patch"), dict) else {}
            patch_out: dict[str, Any] = dict(patch_in)
            for key in ("role", "profile", "notes"):
                if key in patch_out and isinstance(patch_out.get(key), str) and patch_out.get(key).strip():
                    continue
                v = character.get(key)
                if isinstance(v, str) and v.strip():
                    patch_out[key] = v
            if patch_out:
                obj["patch"] = patch_out

            obj.pop("character", None)

        # Drop any unexpected fields to reduce parse failures.
        allowed = {
            "op",
            "name",
            "patch",
            "merge_mode_profile",
            "merge_mode_notes",
            "canonical_name",
            "duplicate_names",
            "reason",
        }
        obj = {k: v for k, v in obj.items() if k in allowed}

        patch2 = obj.get("patch")
        if isinstance(patch2, dict):
            obj["patch"] = {k: patch2.get(k) for k in ("role", "profile", "notes") if k in patch2}

        return obj

    @model_validator(mode="after")
    def _validate_op(self) -> "CharactersAutoUpdateOpV1":
        if self.op == "dedupe":
            if not (self.canonical_name or "").strip():
                raise ValueError("canonical_name is required for dedupe")
            if not self.duplicate_names:
                raise ValueError("duplicate_names is required for dedupe")
            return self

        if self.op == "upsert":
            if not (self.name or "").strip():
                raise ValueError("name is required for upsert")
            if self.patch is None:
                raise ValueError("patch is required for upsert")
            CharacterPatchV1.model_validate(self.patch)
            return self

        raise ValueError("unsupported op")


class CharactersAutoUpdateV1Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: CharactersAutoUpdateSchemaVersion = "characters_auto_update_v1"
    title: str | None = Field(default=None, max_length=255)
    summary_md: str | None = Field(default=None, max_length=MAX_MD_CHARS_V1)
    # Fail-soft: allow ops missing/empty as no-op.
    ops: list[CharactersAutoUpdateOpV1] = Field(default_factory=list, max_length=MAX_OPS_V1)
