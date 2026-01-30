from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal
from app.models.chapter import Chapter
from app.models.character import Character
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
