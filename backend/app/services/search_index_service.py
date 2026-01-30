from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.project_task import ProjectTask
from app.models.outline import Outline
from app.models.search_index import SearchDocument
from app.models.story_memory import StoryMemory
from app.models.worldbook_entry import WorldBookEntry

logger = logging.getLogger("ainovel")

_MAX_TITLE_CHARS = 400
_MAX_CONTENT_CHARS = 6000


@dataclass(frozen=True, slots=True)
class SearchDocInput:
    source_type: str
    source_id: str
    title: str
    content: str
    url_path: str | None = None
    locator_json: str | None = None


def _trim(s: str | None) -> str:
    return (s or "").strip()


def _truncate(s: str, *, limit: int) -> str:
    text = (s or "").strip()
    if not text:
        return ""
    if limit <= 0:
        return text
    return text[:limit]


def _sqlite_table_exists(db: Session, *, name: str) -> bool:
    try:
        dialect = str(getattr(db.get_bind().dialect, "name", "") or "")
    except Exception:
        dialect = ""
    if dialect != "sqlite":
        return False
    try:
        row = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name LIMIT 1"), {"name": name}).first()
        return row is not None
    except Exception:
        return False


def _fts_enabled(db: Session) -> bool:
    return _sqlite_table_exists(db, name="search_index")


def _fts_delete(db: Session, *, rowid: int, title: str, content: str) -> None:
    # External content sync: delete requires the values currently stored in the index.
    db.execute(
        text("INSERT INTO search_index(search_index,rowid,title,content) VALUES('delete',:rowid,:title,:content)"),
        {"rowid": int(rowid), "title": title, "content": content},
    )


def _fts_upsert(db: Session, *, rowid: int, title: str, content: str) -> None:
    db.execute(
        text("INSERT INTO search_index(rowid,title,content) VALUES(:rowid,:title,:content)"),
        {"rowid": int(rowid), "title": title, "content": content},
    )


def upsert_search_document(
    *,
    db: Session,
    project_id: str,
    source_type: str,
    source_id: str,
    title: str,
    content: str,
    url_path: str | None = None,
    locator_json: str | None = None,
) -> SearchDocument:
    st = str(source_type or "").strip()
    sid = str(source_id or "").strip()
    pid = str(project_id or "").strip()
    if not (pid and st and sid):
        raise ValueError("project_id/source_type/source_id are required")

    title_norm = _truncate(_trim(title), limit=_MAX_TITLE_CHARS) or ""
    content_norm = _truncate(_trim(content), limit=_MAX_CONTENT_CHARS) or ""

    row = (
        db.execute(
            select(SearchDocument).where(
                SearchDocument.project_id == pid,
                SearchDocument.source_type == st,
                SearchDocument.source_id == sid,
            )
        )
        .scalars()
        .first()
    )
    fts = _fts_enabled(db)
    if row is None:
        row = SearchDocument(
            project_id=pid,
            source_type=st,
            source_id=sid,
            title=title_norm or None,
            content=content_norm,
            url_path=str(url_path or "").strip() or None,
            locator_json=str(locator_json or "").strip() or None,
            deleted_at=None,
        )
        db.add(row)
        db.flush()
        if fts:
            _fts_upsert(db, rowid=int(row.id), title=title_norm, content=content_norm)
        return row

    old_title = _trim(row.title)
    old_content = _trim(row.content)
    row.title = title_norm or None
    row.content = content_norm
    row.url_path = str(url_path or "").strip() or None
    row.locator_json = str(locator_json or "").strip() or None
    row.deleted_at = None
    db.flush()

    if fts:
        _fts_delete(db, rowid=int(row.id), title=old_title, content=old_content)
        _fts_upsert(db, rowid=int(row.id), title=title_norm, content=content_norm)
    return row


def delete_search_document(*, db: Session, project_id: str, source_type: str, source_id: str) -> bool:
    st = str(source_type or "").strip()
    sid = str(source_id or "").strip()
    pid = str(project_id or "").strip()
    if not (pid and st and sid):
        return False

    row = (
        db.execute(
            select(SearchDocument).where(
                SearchDocument.project_id == pid,
                SearchDocument.source_type == st,
                SearchDocument.source_id == sid,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return False

    if _fts_enabled(db):
        _fts_delete(db, rowid=int(row.id), title=_trim(row.title), content=_trim(row.content))
    db.delete(row)
    return True


def build_project_search_docs(*, db: Session, project_id: str) -> list[SearchDocInput]:
    pid = str(project_id or "").strip()
    if not pid:
        return []

    out: list[SearchDocInput] = []

    chapters = (
        db.execute(select(Chapter).where(Chapter.project_id == pid).order_by(Chapter.updated_at.desc()))
        .scalars()
        .all()
    )
    for c in chapters:
        title = _trim(c.title)
        header = f"第 {int(c.number)} 章：{title}".strip("：")
        content = _trim(c.summary) or _trim(c.content_md)
        if not content:
            continue
        out.append(
            SearchDocInput(
                source_type="chapter",
                source_id=str(c.id),
                title=header,
                content=content,
                url_path=None,
                locator_json=None,
            )
        )

    worldbook = (
        db.execute(select(WorldBookEntry).where(WorldBookEntry.project_id == pid).order_by(WorldBookEntry.updated_at.desc()))
        .scalars()
        .all()
    )
    for w in worldbook:
        title = _trim(w.title)
        content = _trim(w.content_md)
        if not (title or content):
            continue
        out.append(
            SearchDocInput(
                source_type="worldbook_entry",
                source_id=str(w.id),
                title=title or "世界书条目",
                content=(title + "\n\n" + content).strip(),
            )
        )

    characters = (
        db.execute(select(Character).where(Character.project_id == pid).order_by(Character.updated_at.desc()))
        .scalars()
        .all()
    )
    for ch in characters:
        name = _trim(ch.name)
        role = _trim(ch.role)
        profile = _trim(ch.profile)
        notes = _trim(ch.notes)
        body = "\n\n".join([x for x in [role, profile, notes] if x])
        out.append(
            SearchDocInput(
                source_type="character",
                source_id=str(ch.id),
                title=name or "角色卡",
                content=(name + "\n\n" + body).strip(),
            )
        )

    story_memories = (
        db.execute(select(StoryMemory).where(StoryMemory.project_id == pid).order_by(StoryMemory.updated_at.desc()))
        .scalars()
        .all()
    )
    for m in story_memories:
        mt = _trim(getattr(m, "memory_type", "story_memory"))
        title = _trim(m.title) or mt
        content = _trim(m.content)
        if not content:
            continue
        out.append(
            SearchDocInput(
                source_type="story_memory",
                source_id=str(m.id),
                title=title,
                content=(title + "\n\n" + content).strip(),
            )
        )

    outlines = (
        db.execute(select(Outline).where(Outline.project_id == pid).order_by(Outline.updated_at.desc()))
        .scalars()
        .all()
    )
    for o in outlines:
        title = _trim(o.title)
        content = _trim(o.content_md)
        if not (title or content):
            continue
        out.append(
            SearchDocInput(
                source_type="outline",
                source_id=str(o.id),
                title=title or "大纲",
                content=(title + "\n\n" + content).strip(),
            )
        )

    return out


def rebuild_project_search_index(*, db: Session, project_id: str) -> dict[str, Any]:
    """
    Full rebuild at project scope:
    - Compute the desired doc set for the project.
    - Upsert each document.
    - Delete stale docs that are no longer present.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return {"ok": False, "reason": "project_id_empty", "upserted": 0, "deleted": 0}

    docs = build_project_search_docs(db=db, project_id=pid)
    desired = {(d.source_type, d.source_id) for d in docs}

    upserted = 0
    for d in docs:
        upsert_search_document(
            db=db,
            project_id=pid,
            source_type=d.source_type,
            source_id=d.source_id,
            title=d.title,
            content=d.content,
            url_path=d.url_path,
            locator_json=d.locator_json,
        )
        upserted += 1

    deleted = 0
    existing = (
        db.execute(select(SearchDocument).where(SearchDocument.project_id == pid))
        .scalars()
        .all()
    )
    for row in existing:
        key = (str(row.source_type), str(row.source_id))
        if key in desired:
            continue
        if delete_search_document(db=db, project_id=pid, source_type=str(row.source_type), source_id=str(row.source_id)):
            deleted += 1

    return {"ok": True, "project_id": pid, "upserted": int(upserted), "deleted": int(deleted), "fts_enabled": _fts_enabled(db)}


def rebuild_project_search_index_async(*, project_id: str) -> dict[str, Any]:
    """
    Session-owning helper that avoids holding a long transaction while rendering source docs.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return {"ok": False, "reason": "project_id_empty"}

    db_read = SessionLocal()
    try:
        docs = build_project_search_docs(db=db_read, project_id=pid)
    finally:
        db_read.close()

    db_write = SessionLocal()
    try:
        desired = {(d.source_type, d.source_id) for d in docs}

        upserted = 0
        for d in docs:
            upsert_search_document(
                db=db_write,
                project_id=pid,
                source_type=d.source_type,
                source_id=d.source_id,
                title=d.title,
                content=d.content,
                url_path=d.url_path,
                locator_json=d.locator_json,
            )
            upserted += 1

        deleted = 0
        existing = db_write.execute(select(SearchDocument).where(SearchDocument.project_id == pid)).scalars().all()
        for row in existing:
            key = (str(row.source_type), str(row.source_id))
            if key in desired:
                continue
            if delete_search_document(db=db_write, project_id=pid, source_type=str(row.source_type), source_id=str(row.source_id)):
                deleted += 1

        db_write.commit()
        return {"ok": True, "project_id": pid, "upserted": int(upserted), "deleted": int(deleted), "fts_enabled": _fts_enabled(db_write)}
    except Exception as exc:
        db_write.rollback()
        log_event(
            logger,
            "warning",
            event="SEARCH_INDEX_REBUILD_ERROR",
            project_id=pid,
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )
        return {"ok": False, "project_id": pid, "error_type": type(exc).__name__}
    finally:
        db_write.close()


def _fts_query_literal(q: str) -> str:
    s = (q or "").strip()
    if not s:
        return ""
    s = s.replace('"', '""')
    return f"\"{s}\""


def _like_snippet(*, content: str, q: str, window: int = 120) -> str:
    text_s = (content or "").strip()
    q_s = (q or "").strip()
    if not text_s:
        return ""
    if not q_s:
        return _truncate(text_s, limit=window * 2)
    idx = text_s.lower().find(q_s.lower())
    if idx < 0:
        return _truncate(text_s, limit=window * 2)
    start = max(0, idx - window)
    end = min(len(text_s), idx + len(q_s) + window)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text_s) else ""
    return f"{prefix}{text_s[start:end]}{suffix}"


def query_project_search(
    *,
    db: Session,
    project_id: str,
    q: str,
    sources: list[str] | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    q_raw = str(q or "").strip()
    sources_norm = [str(s or "").strip() for s in (sources or []) if str(s or "").strip()]
    limit = max(1, min(int(limit or 20), 200))
    offset = max(0, int(offset or 0))

    if not pid:
        return {"items": [], "next_offset": None, "mode": "none"}
    if not q_raw:
        return {"items": [], "next_offset": None, "mode": "empty"}

    params: dict[str, Any] = {"project_id": pid, "limit": limit, "offset": offset}

    if _fts_enabled(db):
        fts_q = _fts_query_literal(q_raw)
        if not fts_q:
            return {"items": [], "next_offset": None, "mode": "empty"}
        params["q"] = fts_q

        where = "d.project_id = :project_id AND search_index MATCH :q"
        if sources_norm:
            keys: list[str] = []
            for idx, src in enumerate(sources_norm):
                k = f"src_{idx}"
                params[k] = src
                keys.append(f":{k}")
            where += f" AND d.source_type IN ({','.join(keys)})"

        sql = text(
            "SELECT d.source_type,d.source_id,COALESCE(d.title,'') AS title,"
            "snippet(search_index,1,'[',']','...',12) AS snippet,"
            "d.url_path AS jump_url,"
            "bm25(search_index,5.0,1.0) AS rank "
            "FROM search_index JOIN search_documents d ON d.id = search_index.rowid "
            f"WHERE {where} "
            "ORDER BY rank ASC, d.id DESC "
            "LIMIT :limit OFFSET :offset"
        )
        rows = db.execute(sql, params).all()
        items = [
            {
                "source_type": str(r[0] or ""),
                "source_id": str(r[1] or ""),
                "title": str(r[2] or ""),
                "snippet": str(r[3] or ""),
                "jump_url": (str(r[4] or "").strip() or None),
            }
            for r in rows
        ]
        next_offset = (offset + limit) if len(items) >= limit else None
        return {"items": items, "next_offset": next_offset, "mode": "fts", "fts_enabled": True}

    # Fallback: LIKE on normalized documents. Lower quality but keeps the UI usable.
    pattern = f"%{q_raw}%"
    params["pattern"] = pattern
    where = "project_id = :project_id AND (title LIKE :pattern OR content LIKE :pattern)"
    if sources_norm:
        keys = []
        for idx, src in enumerate(sources_norm):
            k = f"src_{idx}"
            params[k] = src
            keys.append(f":{k}")
        where += f" AND source_type IN ({','.join(keys)})"

    rows2 = (
        db.execute(
            text(
                "SELECT source_type,source_id,COALESCE(title,'') AS title,content, url_path "
                "FROM search_documents "
                f"WHERE {where} "
                "ORDER BY updated_at DESC, id DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        .all()
    )
    items2 = [
        {
            "source_type": str(r[0] or ""),
            "source_id": str(r[1] or ""),
            "title": str(r[2] or ""),
            "snippet": _like_snippet(content=str(r[3] or ""), q=q_raw),
            "jump_url": (str(r[4] or "").strip() or None),
        }
        for r in rows2
    ]
    next_offset2 = (offset + limit) if len(items2) >= limit else None
    return {"items": items2, "next_offset": next_offset2, "mode": "like", "fts_enabled": False}


def schedule_search_rebuild_task(
    *,
    db: Session | None = None,
    project_id: str,
    actor_user_id: str | None,
    request_id: str | None,
    reason: str,
) -> str | None:
    """
    Fail-soft scheduler: ensure/enqueue a ProjectTask(kind=search_rebuild) for the project.

    Idempotency key is derived from the latest succeeded search_rebuild task, so a new task can be created after each
    successful rebuild while still deduping bursts of changes.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return None

    reason_norm = str(reason or "").strip() or "dirty"
    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        last = (
            db.execute(
                select(ProjectTask)
                .where(
                    ProjectTask.project_id == pid,
                    ProjectTask.kind == "search_rebuild",
                    ProjectTask.status.in_(["succeeded", "done"]),
                )
                .order_by(ProjectTask.finished_at.desc(), ProjectTask.created_at.desc(), ProjectTask.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        token = "none"
        last_finished_at = getattr(last, "finished_at", None) if last is not None else None
        if last_finished_at is not None:
            token = last_finished_at.isoformat().replace("+00:00", "Z")

        idempotency_key = f"search:project:since:{token}:v1"
        task = (
            db.execute(
                select(ProjectTask).where(
                    ProjectTask.project_id == pid,
                    ProjectTask.idempotency_key == idempotency_key,
                )
            )
            .scalars()
            .first()
        )

        if task is None:
            task = ProjectTask(
                id=new_id(),
                project_id=pid,
                actor_user_id=actor_user_id,
                kind="search_rebuild",
                status="queued",
                idempotency_key=idempotency_key,
                params_json=json.dumps(
                    {"reason": reason_norm, "request_id": request_id, "triggered_at": utc_now().isoformat().replace("+00:00", "Z")},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                result_json=None,
                error_json=None,
            )
            db.add(task)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                task = (
                    db.execute(
                        select(ProjectTask).where(
                            ProjectTask.project_id == pid,
                            ProjectTask.idempotency_key == idempotency_key,
                        )
                    )
                    .scalars()
                    .first()
                )
                if task is None:
                    return None
        else:
            status_norm = str(getattr(task, "status", "") or "").strip().lower()
            if status_norm not in {"queued", "running"}:
                task.status = "queued"
                task.started_at = None
                task.finished_at = None
                task.result_json = None
                task.error_json = None
                db.commit()

        from app.services.task_queue import get_task_queue

        queue = get_task_queue()
        try:
            queue.enqueue(kind="project_task", task_id=str(task.id))
        except Exception as exc:
            fields = exception_log_fields(exc)
            msg = str(fields.get("exception") or str(exc)).replace("\n", " ").strip()[:200]
            task.status = "failed"
            task.finished_at = utc_now()
            task.error_json = json.dumps(
                {"error_type": type(exc).__name__, "message": msg},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            db.commit()
            log_event(
                logger,
                "warning",
                event="PROJECT_TASK_ENQUEUE_ERROR",
                task_id=str(task.id),
                project_id=pid,
                kind="search_rebuild",
                error_type=type(exc).__name__,
                request_id=request_id,
                **fields,
            )
        return str(task.id)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        log_event(
            logger,
            "warning",
            event="SEARCH_REBUILD_SCHEDULE_ERROR",
            project_id=pid,
            error_type=type(exc).__name__,
            request_id=request_id,
            **exception_log_fields(exc),
        )
        return None
    finally:
        if owns_session:
            db.close()
