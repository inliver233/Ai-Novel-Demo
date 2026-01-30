from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import (
    DbDep,
    UserIdDep,
    require_project_editor,
    require_project_viewer,
    require_worldbook_entry_editor,
)
from app.core.config import settings
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.project_settings import ProjectSettings
from app.models.worldbook_entry import WorldBookEntry
from app.schemas.worldbook import (
    WorldBookBulkDeleteRequest,
    WorldBookBulkUpdateRequest,
    WorldBookDuplicateRequest,
    WorldBookEntryCreate,
    WorldBookEntryOut,
    WorldBookEntryUpdate,
    WorldBookExportAllOut,
    WorldBookExportEntryV1,
    WorldBookImportAllRequest,
    WorldBookPreviewTriggerRequest,
)
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.project_task_service import schedule_worldbook_auto_update_task
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task
from app.services.worldbook_service import preview_worldbook_trigger

router = APIRouter()


def _mark_vector_index_dirty(db: DbDep, *, project_id: str) -> None:
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id)
        db.add(row)
        db.flush()
    row.vector_index_dirty = True


def _dedupe_entry_ids(entry_ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in entry_ids:
        value = str(raw or "").strip()
        if not value:
            raise AppError.validation("entry_ids 不能包含空值")
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


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


def _to_out(row: WorldBookEntry) -> dict:
    keywords = _parse_json_list(row.keywords_json)
    return WorldBookEntryOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=row.content_md or "",
        enabled=bool(row.enabled),
        constant=bool(row.constant),
        keywords=keywords,
        exclude_recursion=bool(row.exclude_recursion),
        prevent_recursion=bool(row.prevent_recursion),
        char_limit=int(row.char_limit or 0),
        priority=str(row.priority or "important"),  # type: ignore[arg-type]
        updated_at=row.updated_at,
    ).model_dump()


@router.get("/projects/{project_id}/worldbook_entries")
def list_worldbook_entries(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"worldbook_entries": [_to_out(r) for r in rows]})


@router.post("/projects/{project_id}/worldbook_entries/auto_update")
def trigger_worldbook_auto_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    chapter_id: str | None = Query(default=None, max_length=36),
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    chapter: Chapter | None = None
    if chapter_id is not None and str(chapter_id).strip():
        chapter = db.get(Chapter, str(chapter_id))
        if chapter is None or str(chapter.project_id) != str(project_id):
            raise AppError.not_found("章节不存在")
        if str(getattr(chapter, "status", "") or "") != "done":
            raise AppError.validation(details={"reason": "chapter_not_done"})
    else:
        chapter = (
            db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.status == "done",
                )
                .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    cid = str(getattr(chapter, "id", "") or "").strip() or None
    updated_at = getattr(chapter, "updated_at", None) if chapter is not None else None
    token = updated_at.isoformat().replace("+00:00", "Z") if updated_at is not None else utc_now().isoformat().replace("+00:00", "Z")

    task_id = schedule_worldbook_auto_update_task(
        db=db,
        project_id=project_id,
        actor_user_id=user_id,
        request_id=request_id,
        chapter_id=cid,
        chapter_token=token,
        reason="manual_worldbook_auto_update",
    )
    if not task_id:
        raise AppError.validation(details={"reason": "schedule_failed"})
    return ok_payload(request_id=request_id, data={"task_id": task_id, "chapter_id": cid})


@router.get("/projects/{project_id}/worldbook_entries/export_all")
def export_all_worldbook_entries(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )

    export_obj = WorldBookExportAllOut(
        entries=[
            WorldBookExportEntryV1(
                title=r.title,
                content_md=r.content_md or "",
                enabled=bool(r.enabled),
                constant=bool(r.constant),
                keywords=_parse_json_list(r.keywords_json),
                exclude_recursion=bool(r.exclude_recursion),
                prevent_recursion=bool(r.prevent_recursion),
                char_limit=int(r.char_limit or 0),
                priority=str(r.priority or "important"),  # type: ignore[arg-type]
            )
            for r in rows
        ]
    ).model_dump()
    return ok_payload(request_id=request_id, data={"export": export_obj})


@router.post("/projects/{project_id}/worldbook_entries/import_all")
def import_all_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookImportAllRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    if str(body.schema_version or "").strip() != "worldbook_export_all_v1":
        raise AppError.validation(details={"reason": "unsupported_schema_version", "schema_version": body.schema_version})

    existing = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )
    by_title: dict[str, list[WorldBookEntry]] = {}
    for row in existing:
        key = str(row.title or "").strip()
        by_title.setdefault(key, []).append(row)

    actions: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    created = 0
    updated = 0
    skipped = 0
    deleted = 0

    mode = str(body.mode or "merge").strip()
    if mode == "overwrite":
        deleted = len(existing)
        actions.append({"action": "delete_all", "existing": int(deleted), "incoming": len(body.entries or [])})
        if not body.dry_run:
            for row in existing:
                db.delete(row)
            db.flush()
        by_title = {}

    for item in body.entries or []:
        key = str(item.title or "").strip()
        matches = by_title.get(key) or []
        if len(matches) > 1:
            skipped += 1
            conflicts.append({"title": key, "reason": "multiple_existing", "existing_count": len(matches)})
            actions.append({"title": key, "action": "skip", "reason": "multiple_existing"})
            continue

        keywords = [k.strip() for k in (item.keywords or []) if isinstance(k, str) and k.strip()]
        keywords_json = json.dumps(keywords, ensure_ascii=False) if keywords else "[]"

        if not matches:
            created += 1
            actions.append({"title": key, "action": "create"})
            if body.dry_run:
                continue

            row = WorldBookEntry(
                id=new_id(),
                project_id=project_id,
                title=item.title,
                content_md=item.content_md or "",
                enabled=bool(item.enabled),
                constant=bool(item.constant),
                keywords_json=keywords_json,
                exclude_recursion=bool(item.exclude_recursion),
                prevent_recursion=bool(item.prevent_recursion),
                char_limit=int(item.char_limit),
                priority=str(item.priority),
            )
            db.add(row)
            db.flush()
        else:
            row = matches[0]
            updated += 1
            actions.append({"title": key, "action": "update", "entry_id": row.id})
            if body.dry_run:
                continue

            row.content_md = item.content_md or ""
            row.enabled = bool(item.enabled)
            row.constant = bool(item.constant)
            row.keywords_json = keywords_json
            row.exclude_recursion = bool(item.exclude_recursion)
            row.prevent_recursion = bool(item.prevent_recursion)
            row.char_limit = int(item.char_limit)
            row.priority = str(item.priority)
            row.updated_at = utc_now()

        by_title[key] = [row]

    if body.dry_run:
        return ok_payload(
            request_id=request_id,
            data={
                "dry_run": True,
                "mode": mode,
                "created": int(created),
                "updated": int(updated),
                "deleted": int(deleted),
                "skipped": int(skipped),
                "conflicts": conflicts,
                "actions": actions,
            },
        )

    if created or updated or deleted:
        _mark_vector_index_dirty(db, project_id=project_id)

    db.commit()
    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_import")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_import")
    return ok_payload(
        request_id=request_id,
        data={
            "dry_run": False,
            "mode": mode,
            "created": int(created),
            "updated": int(updated),
            "deleted": int(deleted),
            "skipped": int(skipped),
            "conflicts": conflicts,
            "actions": actions,
        },
    )


@router.post("/projects/{project_id}/worldbook_entries/bulk_update")
def bulk_update_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookBulkUpdateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    entry_ids = _dedupe_entry_ids(body.entry_ids)
    if (
        body.enabled is None
        and body.constant is None
        and body.exclude_recursion is None
        and body.prevent_recursion is None
        and body.char_limit is None
        and body.priority is None
    ):
        raise AppError.validation("至少提供一个更新字段")

    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id, WorldBookEntry.id.in_(entry_ids)))
        .scalars()
        .all()
    )
    by_id = {str(r.id): r for r in rows}
    missing_ids = [eid for eid in entry_ids if eid not in by_id]
    if missing_ids:
        raise AppError.not_found("部分 worldbook_entries 不存在", details={"missing_ids": missing_ids})

    for row in rows:
        if body.enabled is not None:
            row.enabled = bool(body.enabled)
        if body.constant is not None:
            row.constant = bool(body.constant)
        if body.exclude_recursion is not None:
            row.exclude_recursion = bool(body.exclude_recursion)
        if body.prevent_recursion is not None:
            row.prevent_recursion = bool(body.prevent_recursion)
        if body.char_limit is not None:
            row.char_limit = int(body.char_limit)
        if body.priority is not None:
            row.priority = str(body.priority)

    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    for row in rows:
        db.refresh(row)

    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_bulk_update")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_bulk_update")
    return ok_payload(request_id=request_id, data={"worldbook_entries": [_to_out(by_id[eid]) for eid in entry_ids]})


@router.post("/projects/{project_id}/worldbook_entries/bulk_delete")
def bulk_delete_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookBulkDeleteRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    entry_ids = _dedupe_entry_ids(body.entry_ids)
    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id, WorldBookEntry.id.in_(entry_ids)))
        .scalars()
        .all()
    )
    by_id = {str(r.id): r for r in rows}
    missing_ids = [eid for eid in entry_ids if eid not in by_id]
    if missing_ids:
        raise AppError.not_found("部分 worldbook_entries 不存在", details={"missing_ids": missing_ids})

    for row in rows:
        db.delete(row)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_bulk_delete")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_bulk_delete")
    return ok_payload(request_id=request_id, data={"deleted_ids": entry_ids})


@router.post("/projects/{project_id}/worldbook_entries/duplicate")
def duplicate_worldbook_entries(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: WorldBookDuplicateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    entry_ids = _dedupe_entry_ids(body.entry_ids)
    rows = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == project_id, WorldBookEntry.id.in_(entry_ids)))
        .scalars()
        .all()
    )
    by_id = {str(r.id): r for r in rows}
    missing_ids = [eid for eid in entry_ids if eid not in by_id]
    if missing_ids:
        raise AppError.not_found("部分 worldbook_entries 不存在", details={"missing_ids": missing_ids})

    def _copy_title(title: str) -> str:
        suffix = "（复制）"
        base = (title or "").strip()
        if not base:
            base = "（无标题）"
        max_len = 255
        if len(base) + len(suffix) <= max_len:
            return base + suffix
        return base[: max(0, max_len - len(suffix))].rstrip() + suffix

    created: list[WorldBookEntry] = []
    for source_id in entry_ids:
        src = by_id[source_id]
        created.append(
            WorldBookEntry(
                id=new_id(),
                project_id=project_id,
                title=_copy_title(str(src.title or "")),
                content_md=str(src.content_md or ""),
                enabled=bool(src.enabled),
                constant=bool(src.constant),
                keywords_json=src.keywords_json,
                exclude_recursion=bool(src.exclude_recursion),
                prevent_recursion=bool(src.prevent_recursion),
                char_limit=int(src.char_limit or 0),
                priority=str(src.priority or "important"),
            )
        )

    db.add_all(created)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    for row in created:
        db.refresh(row)

    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_duplicate")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_duplicate")
    return ok_payload(request_id=request_id, data={"worldbook_entries": [_to_out(r) for r in created]})


@router.post("/projects/{project_id}/worldbook_entries")
def create_worldbook_entry(
    request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: WorldBookEntryCreate
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    keywords = [k.strip() for k in (body.keywords or []) if isinstance(k, str) and k.strip()]
    keywords_json = json.dumps(keywords, ensure_ascii=False) if keywords else "[]"
    row = WorldBookEntry(
        id=new_id(),
        project_id=project_id,
        title=body.title,
        content_md=body.content_md or "",
        enabled=bool(body.enabled),
        constant=bool(body.constant),
        keywords_json=keywords_json,
        exclude_recursion=bool(body.exclude_recursion),
        prevent_recursion=bool(body.prevent_recursion),
        char_limit=int(body.char_limit),
        priority=str(body.priority),
    )
    db.add(row)
    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_create")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="worldbook_create")
    return ok_payload(request_id=request_id, data={"worldbook_entry": _to_out(row)})


@router.put("/worldbook_entries/{entry_id}")
def update_worldbook_entry(
    request: Request, db: DbDep, user_id: UserIdDep, entry_id: str, body: WorldBookEntryUpdate
) -> dict:
    request_id = request.state.request_id
    row = require_worldbook_entry_editor(db, entry_id=entry_id, user_id=user_id)

    if body.title is not None:
        row.title = body.title
    if body.content_md is not None:
        row.content_md = body.content_md
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.constant is not None:
        row.constant = bool(body.constant)
    if body.keywords is not None:
        keywords = [k.strip() for k in (body.keywords or []) if isinstance(k, str) and k.strip()]
        row.keywords_json = json.dumps(keywords, ensure_ascii=False) if keywords else "[]"
    if body.exclude_recursion is not None:
        row.exclude_recursion = bool(body.exclude_recursion)
    if body.prevent_recursion is not None:
        row.prevent_recursion = bool(body.prevent_recursion)
    if body.char_limit is not None:
        row.char_limit = int(body.char_limit)
    if body.priority is not None:
        row.priority = str(body.priority)

    _mark_vector_index_dirty(db, project_id=str(row.project_id))
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(
        db=db, project_id=str(row.project_id), actor_user_id=user_id, request_id=request_id, reason="worldbook_update"
    )
    schedule_search_rebuild_task(
        db=db, project_id=str(row.project_id), actor_user_id=user_id, request_id=request_id, reason="worldbook_update"
    )
    return ok_payload(request_id=request_id, data={"worldbook_entry": _to_out(row)})


@router.delete("/worldbook_entries/{entry_id}")
def delete_worldbook_entry(request: Request, db: DbDep, user_id: UserIdDep, entry_id: str) -> dict:
    request_id = request.state.request_id
    row = require_worldbook_entry_editor(db, entry_id=entry_id, user_id=user_id)
    db.delete(row)
    _mark_vector_index_dirty(db, project_id=str(row.project_id))
    db.commit()
    schedule_vector_rebuild_task(db=db, project_id=str(row.project_id), actor_user_id=user_id, request_id=request_id, reason="worldbook_delete")
    schedule_search_rebuild_task(db=db, project_id=str(row.project_id), actor_user_id=user_id, request_id=request_id, reason="worldbook_delete")
    return ok_payload(request_id=request_id, data={})


@router.post("/projects/{project_id}/worldbook_entries/preview_trigger")
def preview_trigger(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: WorldBookPreviewTriggerRequest) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    settings_row = db.get(ProjectSettings, project_id)
    qp_cfg = parse_query_preprocessing_config(
        (settings_row.query_preprocessing_json or "").strip() if settings_row is not None else None
    )
    normalized, preprocess_obs = normalize_query_text(query_text=body.query_text, config=qp_cfg)

    result = preview_worldbook_trigger(
        db=db,
        project_id=project_id,
        query_text=normalized,
        include_constant=body.include_constant,
        enable_recursion=body.enable_recursion,
        char_limit=body.char_limit,
    )
    payload = result.model_dump()
    payload["raw_query_text"] = body.query_text
    payload["normalized_query_text"] = normalized
    payload["preprocess_obs"] = preprocess_obs
    payload["match_config"] = {
        "alias_enabled": bool(getattr(settings, "worldbook_match_alias_enabled", False)),
        "pinyin_enabled": bool(getattr(settings, "worldbook_match_pinyin_enabled", False)),
        "regex_enabled": bool(getattr(settings, "worldbook_match_regex_enabled", False)),
        "regex_allowlist_size": len(_parse_json_list(getattr(settings, "worldbook_match_regex_allowlist_json", None))),
        "max_triggered_entries": int(getattr(settings, "worldbook_match_max_triggered_entries", 0) or 0),
    }
    return ok_payload(request_id=request_id, data=payload)
