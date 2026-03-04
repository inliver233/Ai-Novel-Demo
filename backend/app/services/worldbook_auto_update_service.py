from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event, redact_secrets_text
from app.db.session import SessionLocal
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook_auto_update import (
    WorldbookAutoUpdateOpV1,
    WorldbookAutoUpdateSchemaVersion,
    WorldbookEntryCreateV1,
    WorldbookEntryPatchV1,
)
from app.services.generation_service import prepare_llm_call
from app.services.json_repair_service import repair_json_once
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.llm_task_preset_resolver import resolve_task_llm_config
from app.services.llm_retry import (
    LlmRetryExhausted,
    call_llm_and_record_with_retries,
    task_llm_max_attempts,
    task_llm_retry_base_seconds,
    task_llm_retry_jitter,
    task_llm_retry_max_seconds,
)
from app.services.output_contracts import contract_for_task
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task

logger = logging.getLogger("ainovel")


WORLDBOOK_AUTO_UPDATE_TASK = "worldbook_auto_update"
WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION: WorldbookAutoUpdateSchemaVersion = "worldbook_auto_update_v1"

_MAX_EXISTING_TITLES_IN_PROMPT = 200

_ALIAS_SPLIT_RE = re.compile(r"[\s,|;]+")

_CHAPTER_SUMMARY_MAX_CHARS_ENV = "WORLDBOOK_AUTO_UPDATE_CHAPTER_SUMMARY_MAX_CHARS"
_CHAPTER_CONTENT_MAX_CHARS_ENV = "WORLDBOOK_AUTO_UPDATE_CHAPTER_CONTENT_MAX_CHARS"
_DEFAULT_CHAPTER_SUMMARY_MAX_CHARS = 4000
_DEFAULT_CHAPTER_CONTENT_MAX_CHARS = 40000


def _env_int(name: str, *, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return value if value > 0 else default


def _resolve_worldbook_llm_call(
    *,
    db: Session,
    project: Project,
    actor_user_id: str,
) -> tuple[object, str] | None:
    missing_key_exc: AppError | None = None
    try:
        resolved_task = resolve_task_llm_config(
            db,
            project=project,
            user_id=actor_user_id,
            task_key=WORLDBOOK_AUTO_UPDATE_TASK,
            header_api_key=None,
        )
    except OperationalError:
        resolved_task = None
    except AppError as exc:
        if str(exc.code or "") != "LLM_KEY_MISSING":
            raise
        missing_key_exc = exc
        resolved_task = None

    if resolved_task is not None:
        return resolved_task.llm_call, str(resolved_task.api_key)

    preset = db.get(LLMPreset, project.id)
    if preset is None:
        if missing_key_exc is not None:
            raise missing_key_exc
        return None

    api_key = resolve_api_key_for_project(db, project=project, user_id=actor_user_id, header_api_key=None)
    return prepare_llm_call(preset), str(api_key)


def _chapter_summary_max_chars() -> int:
    return _env_int(_CHAPTER_SUMMARY_MAX_CHARS_ENV, default=_DEFAULT_CHAPTER_SUMMARY_MAX_CHARS)


def _chapter_content_max_chars() -> int:
    return _env_int(_CHAPTER_CONTENT_MAX_CHARS_ENV, default=_DEFAULT_CHAPTER_CONTENT_MAX_CHARS)


def _truncate(text: str | None, *, limit: int) -> str:
    raw = str(text or "")
    if len(raw) <= limit:
        return raw
    return raw[:limit]


_EXISTING_ENTRIES_PREVIEW_LIMIT_ENV = "WORLDBOOK_AUTO_UPDATE_EXISTING_ENTRIES_PREVIEW_LIMIT"
_EXISTING_ENTRY_KEYWORDS_LIMIT_ENV = "WORLDBOOK_AUTO_UPDATE_EXISTING_ENTRY_KEYWORDS_LIMIT"
_EXISTING_ENTRY_CONTENT_PREVIEW_CHARS_ENV = "WORLDBOOK_AUTO_UPDATE_EXISTING_ENTRY_CONTENT_PREVIEW_CHARS"
_DEFAULT_EXISTING_ENTRIES_PREVIEW_LIMIT = 60
_DEFAULT_EXISTING_ENTRY_KEYWORDS_LIMIT = 20
_DEFAULT_EXISTING_ENTRY_CONTENT_PREVIEW_CHARS = 400


def _existing_entries_preview_limit() -> int:
    return _env_int(_EXISTING_ENTRIES_PREVIEW_LIMIT_ENV, default=_DEFAULT_EXISTING_ENTRIES_PREVIEW_LIMIT)


def _existing_entry_keywords_limit() -> int:
    return _env_int(_EXISTING_ENTRY_KEYWORDS_LIMIT_ENV, default=_DEFAULT_EXISTING_ENTRY_KEYWORDS_LIMIT)


def _existing_entry_content_preview_chars() -> int:
    return _env_int(_EXISTING_ENTRY_CONTENT_PREVIEW_CHARS_ENV, default=_DEFAULT_EXISTING_ENTRY_CONTENT_PREVIEW_CHARS)


def _build_existing_worldbook_entries_preview_for_prompt(
    rows: list[tuple[object, object, object]] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    limit = _existing_entries_preview_limit()
    kw_limit = _existing_entry_keywords_limit()
    content_limit = _existing_entry_content_preview_chars()
    if limit <= 0:
        return out

    for title, keywords_json, content_md in rows or []:
        title_text = str(title or "").strip()
        if not title_text:
            continue
        keywords = _dedupe_strings(_parse_json_list(str(keywords_json) if keywords_json is not None else None), limit=kw_limit)
        preview_raw = redact_secrets_text(str(content_md or "")).replace("\n", " ").strip()
        preview = _truncate(preview_raw, limit=content_limit).strip()
        out.append({"title": title_text, "keywords": keywords, "content_preview": preview})
        if len(out) >= limit:
            break
    return out


def build_worldbook_auto_update_prompt_v1(
    *,
    project_id: str,
    world_setting: str | None,
    chapter_summary_md: str | None,
    chapter_content_md: str,
    outline_md: str | None,
    existing_worldbook_titles: list[str],
    existing_worldbook_entries_preview: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """
    Prompt contract (v1):

    The model must output a single JSON object with:
    - schema_version: "worldbook_auto_update_v1"
    - title?: string
    - summary_md?: string
    - ops: list of operations (create/update/merge/dedupe)

    Ops strategy (high-level):
    - create: new entry when concept does not exist.
    - update: patch an existing entry matched by title/alias.
    - merge: merge missing details into an existing entry (avoid overwriting good existing content).
    - dedupe: propose canonical_title + duplicates list to merge/delete.
    """

    pid = str(project_id or "").strip()
    world_setting_text = (world_setting or "").strip()
    outline_text = (outline_md or "").strip()
    chapter_summary_text = _truncate((chapter_summary_md or "").strip(), limit=_chapter_summary_max_chars()).strip()
    chapter_content_text = _truncate((chapter_content_md or "").strip(), limit=_chapter_content_max_chars()).strip()

    existing_titles = [str(t or "").strip() for t in (existing_worldbook_titles or []) if str(t or "").strip()][
        :_MAX_EXISTING_TITLES_IN_PROMPT
    ]
    existing_entries_preview = existing_worldbook_entries_preview or []
    existing_entries_preview = existing_entries_preview[: _existing_entries_preview_limit()]

    system = (
        "你是小说写作助手，负责把最新章节/大纲中的关键设定抽取为「世界书条目」自动更新提议。\n"
        "你必须只输出一个 JSON（允许使用 ```json 代码块包裹）。不要输出任何其它文字。\n"
        f"schema_version 必须是 {json.dumps(WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION, ensure_ascii=False)}。\n"
        "ops 是一个数组，每个 op 必须是以下之一：create / update / merge / dedupe。\n"
        "严禁使用错误字段名：不要输出 item；不要输出 content；不要输出 priority:number。\n"
        "priority 必须是字符串枚举之一：drop_first / optional / important / must。\n"
        "每个 op 的字段约定：\n"
        "- create: {op:'create', entry:{title, content_md, keywords, aliases, enabled, constant, exclude_recursion, prevent_recursion, char_limit, priority}, reason?}\n"
        "- update: {op:'update', match_title, entry:{...patch...}, reason?}  # entry 是 patch，可只给需要修改的字段\n"
        "- merge:  {op:'merge',  match_title, merge_mode:'append_missing'|'append'|'replace', entry:{...patch...}, reason?}\n"
        "- dedupe: {op:'dedupe', canonical_title, duplicate_titles:[...], reason?}\n"
        "示例（create）：\n"
        "{\n"
        '  \"schema_version\": \"worldbook_auto_update_v1\",\n'
        '  \"title\": null,\n'
        '  \"summary_md\": null,\n'
        '  \"ops\": [\n'
        "    {\n"
        '      \"op\": \"create\",\n'
        '      \"entry\": {\n'
        '        \"title\": \"某势力\",\n'
        '        \"content_md\": \"...\",\n'
        '        \"keywords\": [\"...\"],\n'
        '        \"aliases\": [\"...\"],\n'
        '        \"enabled\": true,\n'
        '        \"constant\": false,\n'
        '        \"exclude_recursion\": false,\n'
        '        \"prevent_recursion\": false,\n'
        '        \"char_limit\": 12000,\n'
        '        \"priority\": \"important\"\n'
        "      },\n"
        '      \"reason\": \"...\"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "严格遵守：\n"
        "- 不要捏造不存在的设定；信息不足则宁可少写。\n"
        "- 避免重复条目：优先 update/merge，只有不存在才 create。\n"
        "- update/merge 的 match_title 必须严格等于 existing_worldbook_titles 中的某一个 title（忽略大小写）。\n"
        "- 内容更新时优先使用 merge：merge_mode 推荐 append_missing（补全缺失信息，不覆盖已有高质量内容）。\n"
        "- update 更适合修改元数据（enabled/priority/keywords 等）或非常确定的新内容会比旧内容更完整；不要用 update 覆盖更长/更高质量的旧内容。\n"
        "- merge_mode=replace 只在旧内容明显低质量且你提供的是更完整版本时使用，并在 reason 说明取舍。\n"
        "- dedupe 用于指出重复条目并给出 canonical_title 与 duplicate_titles。\n"
        "- keywords/aliases 用于提高触发命中（别名/同义词/外号）。\n"
        "- 尽量填写 op.reason：说明为何 create/update/merge/dedupe，以及你如何避免多/漏/捏造。\n"
    )

    user = (
        f"project_id: {pid}\n\n"
        "=== world_setting ===\n"
        f"{world_setting_text}\n\n"
        "=== existing_worldbook_titles ===\n"
        f"{json.dumps(existing_titles, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "=== existing_worldbook_entries_preview ===\n"
        f"{json.dumps(existing_entries_preview, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "=== outline_md ===\n"
        f"{outline_text}\n\n"
        "=== chapter_summary ===\n"
        f"{chapter_summary_text}\n\n"
        "=== chapter_content_md ===\n"
        f"{chapter_content_text}\n"
    )
    return system, user


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _dedupe_strings(items: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items or []:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if limit > 0 and len(out) >= limit:
            break
    return out


def _build_keywords(*, title: str, keywords: list[str] | None, aliases: list[str] | None) -> list[str]:
    base: list[str] = [str(title or "").strip()]
    base.extend([str(k or "").strip() for k in (keywords or [])])
    base.extend([str(a or "").strip() for a in (aliases or [])])
    return _dedupe_strings(base, limit=40)


def _split_alias_tokens(keyword: str) -> list[str]:
    k = (keyword or "").strip()
    if not k:
        return []
    k_lower = k.lower()
    if k_lower.startswith("alias:") or k_lower.startswith("aliases:"):
        raw = k.split(":", 1)[1].strip()
    elif "|" in k:
        raw = k
    else:
        return []
    return [p.strip() for p in _ALIAS_SPLIT_RE.split(raw) if p.strip()]


def merge_worldbook_markdown(*, old: str, new: str, mode: str) -> str:
    """
    Helper used by LMEM-641:
    - append_missing: if old is empty -> new else keep old
    - append: append new under old with a separator when both exist
    - replace: always replace with new if new is non-empty
    """

    old_s = (old or "").strip()
    new_s = (new or "").strip()
    mode_norm = str(mode or "").strip().lower() or "append_missing"

    if not new_s:
        return old_s
    if mode_norm == "replace":
        return new_s
    if mode_norm == "append":
        if not old_s:
            return new_s
        return f"{old_s}\n\n---\n\n{new_s}".strip()
    # default: append_missing
    return new_s if not old_s else old_s


def apply_worldbook_auto_update_ops(*, db: Session, project_id: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Applies parsed WorldbookAutoUpdateOpV1 operations to DB.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return {"ok": False, "reason": "project_id_empty", "created": 0, "updated": 0, "deleted": 0, "skipped": 0}

    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == pid).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )

    by_title: dict[str, WorldBookEntry] = {}
    by_key: dict[str, WorldBookEntry] = {}
    keys_by_id: dict[str, set[str]] = {}

    def _reindex_entry(entry: WorldBookEntry) -> None:
        eid = str(getattr(entry, "id", "") or "")
        old_keys = keys_by_id.get(eid, set())
        for key in old_keys:
            if by_key.get(key) is entry:
                by_key.pop(key, None)
            if by_title.get(key) is entry:
                by_title.pop(key, None)

        title_key = str(getattr(entry, "title", "") or "").strip().lower()
        next_keys: set[str] = set()
        if title_key:
            by_title[title_key] = entry
            next_keys.add(title_key)
        for raw_keyword in _parse_json_list(getattr(entry, "keywords_json", None)):
            keyword_key = str(raw_keyword or "").strip().lower()
            if not keyword_key:
                continue
            next_keys.add(keyword_key)
            for alias in _split_alias_tokens(str(raw_keyword or "")):
                alias_key = alias.strip().lower()
                if alias_key:
                    next_keys.add(alias_key)

        keys_by_id[eid] = next_keys
        for key in next_keys:
            by_key.setdefault(key, entry)

    def _unindex_entry(entry: WorldBookEntry) -> None:
        eid = str(getattr(entry, "id", "") or "")
        for key in keys_by_id.get(eid, set()):
            if by_key.get(key) is entry:
                by_key.pop(key, None)
            if by_title.get(key) is entry:
                by_title.pop(key, None)
        keys_by_id.pop(eid, None)

    for row in rows:
        _reindex_entry(row)

    def _find_entry(match: str) -> WorldBookEntry | None:
        key = str(match or "").strip().lower()
        if not key:
            return None
        return by_title.get(key) or by_key.get(key)

    created_ids: list[str] = []
    updated_ids: list[str] = []
    deleted_ids: list[str] = []
    skipped: list[dict[str, Any]] = []

    for idx, raw in enumerate(ops or []):
        try:
            op = WorldbookAutoUpdateOpV1.model_validate(raw)
        except Exception:
            skipped.append({"index": idx, "reason": "invalid_op_schema"})
            continue

        if op.op == "dedupe":
            canonical_title = (op.canonical_title or "").strip()
            canon = _find_entry(canonical_title)
            if canon is None:
                skipped.append({"index": idx, "reason": "canonical_not_found", "canonical_title": canonical_title})
                continue

            canon_keywords = _parse_json_list(getattr(canon, "keywords_json", None))
            merged_keywords = list(canon_keywords)
            merged_content = str(canon.content_md or "")

            for dt in op.duplicate_titles:
                t = str(dt or "").strip()
                if not t:
                    continue
                dup = _find_entry(t)
                if dup is None:
                    continue
                if str(dup.id) == str(canon.id):
                    continue
                merged_content = merge_worldbook_markdown(old=merged_content, new=str(dup.content_md or ""), mode="append")
                merged_keywords.extend(_parse_json_list(getattr(dup, "keywords_json", None)))
                db.delete(dup)
                deleted_ids.append(str(dup.id))
                _unindex_entry(dup)

            canon.content_md = merged_content
            canon.keywords_json = json.dumps(_dedupe_strings(merged_keywords, limit=40), ensure_ascii=False) if merged_keywords else "[]"
            updated_ids.append(str(canon.id))
            _reindex_entry(canon)
            continue

        if op.op == "create":
            try:
                entry = WorldbookEntryCreateV1.model_validate(op.entry)
            except Exception:
                skipped.append({"index": idx, "reason": "create_entry_invalid"})
                continue
            title = str(entry.title or "").strip()
            if not title:
                skipped.append({"index": idx, "reason": "title_empty"})
                continue
            existing = _find_entry(title)
            if existing is not None:
                # Treat create as merge to keep idempotent-ish.
                merged = merge_worldbook_markdown(old=str(existing.content_md or ""), new=str(entry.content_md or ""), mode="append_missing")
                existing.content_md = merged

                existing_keywords = _parse_json_list(getattr(existing, "keywords_json", None))
                merged_keywords = list(existing_keywords)
                merged_keywords.extend(list(entry.keywords or []))
                merged_keywords.extend(list(entry.aliases or []))
                merged_keywords.insert(0, str(existing.title or title))
                existing.keywords_json = (
                    json.dumps(_dedupe_strings(merged_keywords, limit=40), ensure_ascii=False) if merged_keywords else "[]"
                )
                updated_ids.append(str(existing.id))
                _reindex_entry(existing)
                continue

            keywords = _build_keywords(title=title, keywords=list(entry.keywords or []), aliases=list(entry.aliases or []))
            row = WorldBookEntry(
                id=new_id(),
                project_id=pid,
                title=title,
                content_md=str(entry.content_md or ""),
                enabled=bool(entry.enabled),
                constant=bool(entry.constant),
                keywords_json=json.dumps(keywords, ensure_ascii=False) if keywords else "[]",
                exclude_recursion=bool(entry.exclude_recursion),
                prevent_recursion=bool(entry.prevent_recursion),
                char_limit=int(entry.char_limit),
                priority=str(entry.priority or "important"),
            )
            db.add(row)
            created_ids.append(str(row.id))
            _reindex_entry(row)
            continue

        if op.op in {"update", "merge"}:
            match_title = str(op.match_title or "").strip()
            if not match_title:
                skipped.append({"index": idx, "reason": "match_title_empty"})
                continue
            target = _find_entry(match_title)
            if target is None:
                skipped.append({"index": idx, "reason": "match_title_not_found", "match_title": match_title})
                continue
            try:
                patch = WorldbookEntryPatchV1.model_validate(op.entry)
            except Exception:
                skipped.append({"index": idx, "reason": "patch_entry_invalid"})
                continue
            if patch.title is not None and patch.title.strip():
                next_title = patch.title.strip()
                target.title = next_title

            if patch.content_md is not None:
                if op.op == "merge":
                    target.content_md = merge_worldbook_markdown(
                        old=str(target.content_md or ""),
                        new=str(patch.content_md or ""),
                        mode=str(op.merge_mode or "append_missing"),
                    )
                else:
                    old_s = str(target.content_md or "").strip()
                    new_s = str(patch.content_md or "").strip()
                    if not new_s:
                        # Do not wipe existing content via update.
                        pass
                    elif not old_s:
                        target.content_md = new_s
                    elif len(new_s) < int(len(old_s) * 0.8):
                        # Avoid overwriting potentially high-quality content with a shorter patch.
                        target.content_md = merge_worldbook_markdown(old=old_s, new=new_s, mode="append")
                    else:
                        target.content_md = new_s

            if patch.enabled is not None:
                target.enabled = bool(patch.enabled)
            if patch.constant is not None:
                target.constant = bool(patch.constant)
            if patch.exclude_recursion is not None:
                target.exclude_recursion = bool(patch.exclude_recursion)
            if patch.prevent_recursion is not None:
                target.prevent_recursion = bool(patch.prevent_recursion)
            if patch.char_limit is not None:
                target.char_limit = int(patch.char_limit)
            if patch.priority is not None and patch.priority.strip():
                target.priority = patch.priority.strip()

            if patch.keywords is not None or patch.aliases is not None:
                existing_keywords = _parse_json_list(getattr(target, "keywords_json", None))
                merged_keywords = list(existing_keywords)
                merged_keywords.extend(list(patch.keywords or []) if patch.keywords is not None else [])
                merged_keywords.extend(list(patch.aliases or []) if patch.aliases is not None else [])
                merged_keywords.insert(0, str(target.title or ""))
                target.keywords_json = json.dumps(_dedupe_strings(merged_keywords, limit=40), ensure_ascii=False) if merged_keywords else "[]"

            updated_ids.append(str(target.id))
            _reindex_entry(target)
            continue

        skipped.append({"index": idx, "reason": "unsupported_op"})

    changed = bool(created_ids or updated_ids or deleted_ids)
    if not changed:
        return {
            "ok": True,
            "project_id": pid,
            "created_ids": created_ids,
            "updated_ids": updated_ids,
            "deleted_ids": deleted_ids,
            "created": len(created_ids),
            "updated": len(updated_ids),
            "deleted": len(deleted_ids),
            "skipped": len(skipped),
            "skipped_items": skipped,
            "no_op": True,
        }

    settings_row = db.get(ProjectSettings, pid)
    if settings_row is None:
        settings_row = ProjectSettings(project_id=pid)
        db.add(settings_row)
    settings_row.vector_index_dirty = True

    db.commit()

    schedule_vector_rebuild_task(db=db, project_id=pid, actor_user_id=None, request_id=None, reason="worldbook_auto_update")
    schedule_search_rebuild_task(db=db, project_id=pid, actor_user_id=None, request_id=None, reason="worldbook_auto_update")

    return {
        "ok": True,
        "project_id": pid,
        "created_ids": created_ids,
        "updated_ids": updated_ids,
        "deleted_ids": deleted_ids,
        "created": len(created_ids),
        "updated": len(updated_ids),
        "deleted": len(deleted_ids),
        "skipped": len(skipped),
        "skipped_items": skipped,
        "no_op": False,
    }


def worldbook_auto_update_v1(
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    chapter_id: str | None,
) -> dict[str, Any]:
    """
    End-to-end worldbook auto update:
    - read project/chapter/outline/settings + existing titles
    - call LLM and parse ops
    - apply ops to DB

    Fail-soft: returns {"ok": False, ...} instead of raising.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return {"ok": False, "reason": "project_id_empty"}

    chapter_summary = ""
    chapter_content = ""
    outline_text = ""
    world_setting = ""
    existing_titles: list[str] = []
    existing_entries_preview: list[dict[str, Any]] = []
    project: Project | None = None
    llm_call = None
    api_key = ""

    db_read = SessionLocal()
    try:
        project = db_read.get(Project, pid)
        if project is None:
            return {"ok": False, "project_id": pid, "reason": "project_not_found"}

        try:
            resolved = _resolve_worldbook_llm_call(db=db_read, project=project, actor_user_id=actor_user_id)
        except Exception as exc:
            safe_message = redact_secrets_text(str(exc)).replace("\n", " ").strip()
            if not safe_message:
                safe_message = type(exc).__name__
            return {
                "ok": False,
                "project_id": pid,
                "reason": "api_key_missing",
                "error_type": type(exc).__name__,
                "error_message": safe_message[:400],
            }
        if resolved is None:
            return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}
        llm_call, api_key = resolved

        settings_row = db_read.get(ProjectSettings, pid)
        world_setting = (settings_row.world_setting if settings_row else "") or ""

        if chapter_id:
            c = db_read.get(Chapter, str(chapter_id))
            if c is not None and str(getattr(c, "project_id", "")) == pid:
                chapter_summary = str(getattr(c, "summary", "") or "").strip()
                chapter_content = str(getattr(c, "content_md", "") or "").strip()

        outline_id = getattr(project, "active_outline_id", None) if project is not None else None
        outline_row = db_read.get(Outline, str(outline_id)) if outline_id else None
        if outline_row is None:
            outline_row = (
                db_read.execute(select(Outline).where(Outline.project_id == pid).order_by(Outline.updated_at.desc()).limit(1))
                .scalars()
                .first()
            )
        if outline_row is not None:
            outline_text = str(getattr(outline_row, "content_md", "") or "").strip()

        rows = (
            db_read.execute(
                select(WorldBookEntry.title)
                .where(WorldBookEntry.project_id == pid)
                .order_by(WorldBookEntry.updated_at.desc())
                .limit(_MAX_EXISTING_TITLES_IN_PROMPT)
            )
            .scalars()
            .all()
        )
        existing_titles = [str(t or "").strip() for t in rows if str(t or "").strip()]

        preview_rows = (
            db_read.execute(
                select(WorldBookEntry.title, WorldBookEntry.keywords_json, WorldBookEntry.content_md)
                .where(WorldBookEntry.project_id == pid)
                .order_by(WorldBookEntry.updated_at.desc())
                .limit(_existing_entries_preview_limit())
            )
            .all()
        )
        existing_entries_preview = _build_existing_worldbook_entries_preview_for_prompt(preview_rows)
    finally:
        db_read.close()

    if project is None or llm_call is None:
        return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}

    system, user = build_worldbook_auto_update_prompt_v1(
        project_id=pid,
        world_setting=world_setting,
        chapter_summary_md=chapter_summary,
        chapter_content_md=chapter_content,
        outline_md=outline_text,
        existing_worldbook_titles=existing_titles,
        existing_worldbook_entries_preview=existing_entries_preview,
    )

    llm_attempts: list[dict[str, Any]] = []

    try:
        base_max_tokens = llm_call.params.get("max_tokens")

        def _clamp_max_tokens(limit: int) -> int:
            if isinstance(base_max_tokens, int) and base_max_tokens > 0:
                return min(int(limit), int(base_max_tokens))
            return int(limit)

        retry_system = (
            system
            + "\n"
            + "【重试模式】上一轮调用失败/超时。请输出更短、更保守的更新提议：\n"
            + "- 只输出裸 JSON（不要 Markdown，不要代码块）\n"
            + "- ops 数量 <= 8；只处理最确定的条目，不要穷举\n"
            + "- 严格遵守字段名与 schema_version（尤其是 entry.content_md/keywords/aliases/priority 等）\n"
        )

        max_attempts = task_llm_max_attempts(default=3)
        recorded, llm_attempts = call_llm_and_record_with_retries(
            logger=logger,
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=pid,
            chapter_id=str(chapter_id) if chapter_id else None,
            run_type="worldbook_auto_update",
            api_key=api_key,
            prompt_system=system,
            prompt_user=user,
            llm_call=llm_call,
            memory_retrieval_log_json=None,
            run_params_extra_json={"task": WORLDBOOK_AUTO_UPDATE_TASK, "schema_version": WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION},
            max_attempts=max_attempts,
            retry_prompt_system=retry_system,
            llm_call_overrides_by_attempt={
                1: {"temperature": 0.2, "max_tokens": _clamp_max_tokens(2048)},
                2: {"temperature": 0.1, "max_tokens": _clamp_max_tokens(1024)},
                3: {"temperature": 0.0, "max_tokens": _clamp_max_tokens(512)},
            },
            backoff_base_seconds=task_llm_retry_base_seconds(),
            backoff_max_seconds=task_llm_retry_max_seconds(),
            jitter=task_llm_retry_jitter(),
        )
    except LlmRetryExhausted as exc:
        log_event(
            logger,
            "warning",
            event="WORLDBOOK_AUTO_UPDATE_LLM_ERROR",
            project_id=pid,
            chapter_id=str(chapter_id or ""),
            run_id=exc.run_id,
            error_type=str(exc.error_type),
            request_id=request_id,
            **exception_log_fields(exc.last_exception),
        )
        return {
            "ok": False,
            "project_id": pid,
            "reason": "llm_call_failed",
            "run_id": exc.run_id,
            "error_type": exc.error_type,
            "error_message": exc.error_message[:400],
            "attempts": list(exc.attempts or []),
            "error": {
                "code": exc.error_code or "LLM_CALL_FAILED",
                "details": {"attempts": list(exc.attempts or [])},
            },
        }

    contract = contract_for_task(WORLDBOOK_AUTO_UPDATE_TASK)
    parsed = contract.parse(recorded.text or "", finish_reason=recorded.finish_reason)

    repair_run_id: str | None = None
    warnings = list(parsed.warnings or [])
    if len(list(llm_attempts or [])) >= 2:
        warnings.append("llm_retry_used")

    if parsed.parse_error is not None:
        repair_schema = (
            "{\n"
            '  "schema_version": "worldbook_auto_update_v1",\n'
            '  "title": string | null,\n'
            '  "summary_md": string | null,\n'
            '  "ops": [\n'
            '    {\n'
            '      "op": "create" | "update" | "merge" | "dedupe",\n'
            '      "match_title": string,\n'
            '      "entry": {\n'
            '        "title": string,\n'
            '        "content_md": string,\n'
            '        "keywords": [string],\n'
            '        "aliases": [string],\n'
            '        "priority": string\n'
            "      },\n"
            '      "merge_mode": "append_missing" | "append" | "replace",\n'
            '      "canonical_title": string,\n'
            '      "duplicate_titles": [string],\n'
            '      "reason": string | null\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        repair_req = f"{request_id}:repair"
        if len(repair_req) > 64:
            repair_req = repair_req[:64]
        repair = repair_json_once(
            request_id=repair_req,
            actor_user_id=actor_user_id,
            project_id=pid,
            chapter_id=str(chapter_id) if chapter_id else None,
            api_key=api_key,
            llm_call=llm_call,
            raw_output=recorded.text,
            schema=repair_schema,
            expected_root="object",
            origin_run_id=recorded.run_id,
            origin_task=WORLDBOOK_AUTO_UPDATE_TASK,
        )
        repair_run_id = str(repair.get("repair_run_id") or "").strip() or None
        warnings.extend(list(repair.get("warnings") or []))

        if bool(repair.get("ok")):
            repaired_text = str(repair.get("raw_json") or "").strip()
            parsed2 = contract.parse(repaired_text, finish_reason=str(repair.get("finish_reason") or "").strip() or None)
            if parsed2.parse_error is None:
                parsed = parsed2
                warnings = list(parsed.warnings or []) + list(repair.get("warnings") or [])
            else:
                payload: dict[str, Any] = {
                    "parse_error": parsed2.parse_error,
                    "original_parse_error": parsed.parse_error,
                    "repair_run_id": repair_run_id,
                }
                parse_error_text = json.dumps(payload, ensure_ascii=False)
                return {
                    "ok": False,
                    "project_id": pid,
                    "reason": "parse_error",
                    "run_id": recorded.run_id,
                    "warnings": warnings,
                    "parse_error": parse_error_text,
                    "error_message": parse_error_text[:400] if parse_error_text else None,
                }
        else:
            payload = {
                "original_parse_error": parsed.parse_error,
                "repair_reason": repair.get("reason"),
                "repair_parse_error": repair.get("parse_error"),
                "repair_error_message": repair.get("error_message"),
                "repair_run_id": repair_run_id,
            }
            parse_error_text = json.dumps(payload, ensure_ascii=False)
            return {
                "ok": False,
                "project_id": pid,
                "reason": "parse_error",
                "run_id": recorded.run_id,
                "warnings": warnings,
                "parse_error": parse_error_text,
                "error_message": parse_error_text[:400] if parse_error_text else None,
            }

    db_write = SessionLocal()
    try:
        applied = apply_worldbook_auto_update_ops(db=db_write, project_id=pid, ops=list(parsed.data.get("ops") or []))
    except Exception as exc:
        try:
            db_write.rollback()
        except Exception:
            pass
        log_event(
            logger,
            "warning",
            event="WORLDBOOK_AUTO_UPDATE_APPLY_ERROR",
            project_id=pid,
            chapter_id=str(chapter_id or ""),
            error_type=type(exc).__name__,
            request_id=request_id,
            **exception_log_fields(exc),
        )
        safe_message = redact_secrets_text(str(exc)).replace("\n", " ").strip()
        if not safe_message:
            safe_message = type(exc).__name__
        return {
            "ok": False,
            "project_id": pid,
            "reason": "apply_failed",
            "error_type": type(exc).__name__,
            "error_message": (f"{safe_message[:360]} (repair_run_id={repair_run_id})" if repair_run_id else safe_message[:400]),
            "run_id": recorded.run_id,
        }
    finally:
        db_write.close()

    return {
        "ok": True,
        "project_id": pid,
        "run_id": recorded.run_id,
        "repair_run_id": repair_run_id,
        "warnings": warnings,
        "applied": applied,
    }
