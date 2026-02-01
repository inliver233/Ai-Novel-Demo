from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.services.generation_service import call_llm_and_record, prepare_llm_call
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.output_contracts import contract_for_task
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task

logger = logging.getLogger("ainovel")


WORLDBOOK_AUTO_UPDATE_TASK = "worldbook_auto_update"
WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION: WorldbookAutoUpdateSchemaVersion = "worldbook_auto_update_v1"

_MAX_EXISTING_TITLES_IN_PROMPT = 200

_ALIAS_SPLIT_RE = re.compile(r"[\s,|;]+")


def build_worldbook_auto_update_prompt_v1(
    *,
    project_id: str,
    world_setting: str | None,
    chapter_content_md: str,
    outline_md: str | None,
    existing_worldbook_titles: list[str],
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
    chapter_text = (chapter_content_md or "").strip()

    existing_titles = [str(t or "").strip() for t in (existing_worldbook_titles or []) if str(t or "").strip()][
        :_MAX_EXISTING_TITLES_IN_PROMPT
    ]

    system = (
        "你是小说写作助手，负责把最新章节/大纲中的关键设定抽取为「世界书条目」自动更新提议。\n"
        "你必须只输出一个 JSON（允许使用 ```json 代码块包裹）。不要输出任何其它文字。\n"
        f"schema_version 必须是 {json.dumps(WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION, ensure_ascii=False)}。\n"
        "ops 是一个数组，每个 op 必须是以下之一：create / update / merge / dedupe。\n"
        "严格遵守：\n"
        "- 不要捏造不存在的设定；信息不足则宁可少写。\n"
        "- 避免重复条目：优先 update/merge，只有不存在才 create。\n"
        "- update/merge 的 match_title 必须严格等于 existing_worldbook_titles 中的某一个 title（忽略大小写）。\n"
        "- merge 时倾向补全缺失信息（append_missing），不要覆盖已有内容。\n"
        "- dedupe 用于指出重复条目并给出 canonical_title 与 duplicate_titles。\n"
        "- keywords/aliases 用于提高触发命中（别名/同义词/外号）。\n"
    )

    user = (
        f"project_id: {pid}\n\n"
        "=== world_setting ===\n"
        f"{world_setting_text}\n\n"
        "=== existing_worldbook_titles ===\n"
        f"{json.dumps(existing_titles, ensure_ascii=False)}\n\n"
        "=== outline_md ===\n"
        f"{outline_text}\n\n"
        "=== chapter_content_md ===\n"
        f"{chapter_text}\n"
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
                existing.enabled = bool(entry.enabled)
                existing.constant = bool(entry.constant)
                existing.exclude_recursion = bool(entry.exclude_recursion)
                existing.prevent_recursion = bool(entry.prevent_recursion)
                existing.char_limit = int(entry.char_limit)
                existing.priority = str(entry.priority or "important")
                existing.keywords_json = json.dumps(
                    _build_keywords(title=title, keywords=list(entry.keywords or []), aliases=list(entry.aliases or [])),
                    ensure_ascii=False,
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
                    target.content_md = str(patch.content_md or "")

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

    chapter_text = ""
    outline_text = ""
    world_setting = ""
    existing_titles: list[str] = []
    preset: LLMPreset | None = None
    project: Project | None = None

    db_read = SessionLocal()
    try:
        project = db_read.get(Project, pid)
        if project is None:
            return {"ok": False, "project_id": pid, "reason": "project_not_found"}

        preset = db_read.get(LLMPreset, pid)
        if preset is None:
            return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}

        settings_row = db_read.get(ProjectSettings, pid)
        world_setting = (settings_row.world_setting if settings_row else "") or ""

        if chapter_id:
            c = db_read.get(Chapter, str(chapter_id))
            if c is not None and str(getattr(c, "project_id", "")) == pid:
                chapter_text = (str(getattr(c, "summary", "") or "").strip() or str(getattr(c, "content_md", "") or "").strip())

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
            db_read.execute(select(WorldBookEntry.title).where(WorldBookEntry.project_id == pid).order_by(WorldBookEntry.updated_at.desc()))
            .scalars()
            .all()
        )
        existing_titles = [str(t or "").strip() for t in rows if str(t or "").strip()]
    finally:
        db_read.close()

    if preset is None or project is None:
        return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}

    system, user = build_worldbook_auto_update_prompt_v1(
        project_id=pid,
        world_setting=world_setting,
        chapter_content_md=chapter_text,
        outline_md=outline_text,
        existing_worldbook_titles=existing_titles,
    )

    try:
        db_key = SessionLocal()
        try:
            api_key = resolve_api_key_for_project(db_key, project=project, user_id=actor_user_id, header_api_key=None)
        finally:
            db_key.close()
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

    llm_call = prepare_llm_call(preset)

    try:
        recorded = call_llm_and_record(
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
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="WORLDBOOK_AUTO_UPDATE_LLM_ERROR",
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
            "reason": "llm_call_failed",
            "error_type": type(exc).__name__,
            "error_message": safe_message[:400],
        }

    contract = contract_for_task(WORLDBOOK_AUTO_UPDATE_TASK)
    parsed = contract.parse(recorded.text or "", finish_reason=recorded.finish_reason)
    if parsed.parse_error is not None:
        parse_error = str(parsed.parse_error or "").strip()
        return {
            "ok": False,
            "project_id": pid,
            "reason": "parse_error",
            "run_id": recorded.run_id,
            "warnings": parsed.warnings,
            "parse_error": parse_error,
            "error_message": parse_error[:400] if parse_error else None,
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
            "error_message": safe_message[:400],
            "run_id": recorded.run_id,
        }
    finally:
        db_write.close()

    return {"ok": True, "project_id": pid, "run_id": recorded.run_id, "warnings": parsed.warnings, "applied": applied}
