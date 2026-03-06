from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.project_task import ProjectTask
from app.models.outline import Outline
from app.models.project_source_document import ProjectSourceDocument
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.search_index import SearchDocument
from app.models.story_memory import StoryMemory
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryRelation
from app.models.worldbook_entry import WorldBookEntry
from app.services.project_task_event_service import emit_and_enqueue_project_task, reset_project_task_to_queued

logger = logging.getLogger("ainovel")

_MAX_TITLE_CHARS = 400
_MAX_CONTENT_CHARS = 6000
_MAX_QUERY_TERMS = 8

_SAFE_FTS_TERM_RE = re.compile(r"^[0-9A-Za-z_]+$")


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


def _has_table(db: Session, *, name: str) -> bool:
    try:
        return bool(inspect(db.get_bind()).has_table(name))
    except Exception:
        return False


def _render_table_row_text(data_json: str | None) -> str:
    raw = _trim(data_json)
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
    except Exception:
        return raw

    if isinstance(obj, dict):
        parts: list[str] = []
        for k in sorted(obj.keys(), key=lambda x: str(x)):
            v = obj.get(k)
            if v is None:
                continue
            v_s = _trim(str(v))
            if not v_s:
                continue
            parts.append(f"{k}: {v_s}")
        return "\n".join(parts).strip()

    if isinstance(obj, list):
        parts = [_trim(str(x)) for x in obj if _trim(str(x))]
        if parts:
            return "\n".join(parts[:50]).strip()

    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return raw


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
        plan = _trim(getattr(c, "plan", None))
        summary = _trim(getattr(c, "summary", None))
        content_md = _trim(getattr(c, "content_md", None))
        content = "\n\n".join([x for x in [header, plan, summary, content_md] if x]).strip()
        if not (summary or content_md):
            continue
        out.append(
            SearchDocInput(
                source_type="chapter",
                source_id=str(c.id),
                title=header,
                content=content,
                url_path=f"/projects/{pid}/writing?chapterId={str(c.id)}",
                locator_json=json.dumps({"chapter_id": str(c.id)}, ensure_ascii=False),
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
        kw_text = ""
        kw_raw = _trim(getattr(w, "keywords_json", None))
        if kw_raw:
            try:
                kw_obj = json.loads(kw_raw)
            except Exception:
                kw_obj = None
            if isinstance(kw_obj, list):
                kws = [_trim(str(x)) for x in kw_obj if _trim(str(x))]
                kw_text = "\n".join(kws[:50]).strip()
            else:
                kw_text = kw_raw

        if not (title or content or kw_text):
            continue
        out.append(
            SearchDocInput(
                source_type="worldbook_entry",
                source_id=str(w.id),
                title=title or "世界书条目",
                content="\n\n".join([x for x in [title, content, kw_text] if x]).strip(),
                url_path=f"/projects/{pid}/worldbook",
                locator_json=json.dumps({"worldbook_entry_id": str(w.id)}, ensure_ascii=False),
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
                url_path=f"/projects/{pid}/characters",
                locator_json=json.dumps({"character_id": str(ch.id)}, ensure_ascii=False),
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
        full_context = _trim(getattr(m, "full_context_md", None))
        if not (content or full_context):
            continue
        out.append(
            SearchDocInput(
                source_type="story_memory",
                source_id=str(m.id),
                title=title,
                content="\n\n".join([x for x in [title, content, full_context] if x]).strip(),
                url_path=f"/projects/{pid}/chapter-analysis?chapterId={str(getattr(m, 'chapter_id', '') or '').strip()}"
                if _trim(getattr(m, 'chapter_id', '') or '')
                else f"/projects/{pid}/chapter-analysis",
                locator_json=json.dumps(
                    {"story_memory_id": str(m.id), "chapter_id": str(getattr(m, "chapter_id", "") or "").strip() or None},
                    ensure_ascii=False,
                ),
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
                url_path=f"/projects/{pid}/outline",
                locator_json=json.dumps({"outline_id": str(o.id)}, ensure_ascii=False),
            )
        )

    if _has_table(db, name="project_source_documents"):
        source_docs = (
            db.execute(
                select(ProjectSourceDocument)
                .where(ProjectSourceDocument.project_id == pid)
                .order_by(ProjectSourceDocument.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for d in source_docs:
            filename = _trim(getattr(d, "filename", ""))
            content = _trim(getattr(d, "content_text", ""))
            content_type = _trim(getattr(d, "content_type", ""))
            if not (filename or content):
                continue
            title = filename or "导入文档"
            body = "\n\n".join([x for x in [filename, content_type, content] if x]).strip()
            out.append(
                SearchDocInput(
                    source_type="source_document",
                    source_id=str(d.id),
                    title=title,
                    content=body,
                    url_path=f"/projects/{pid}/import?docId={str(d.id)}",
                    locator_json=json.dumps({"document_id": str(d.id)}, ensure_ascii=False),
                )
            )

    if _has_table(db, name="project_tables") and _has_table(db, name="project_table_rows"):
        tables = (
            db.execute(select(ProjectTable).where(ProjectTable.project_id == pid).order_by(ProjectTable.updated_at.desc()))
            .scalars()
            .all()
        )
        table_by_id: dict[str, ProjectTable] = {str(t.id): t for t in tables}

        rows = (
            db.execute(
                select(ProjectTableRow)
                .where(ProjectTableRow.project_id == pid)
                .order_by(ProjectTableRow.updated_at.desc(), ProjectTableRow.id.desc())
            )
            .scalars()
            .all()
        )
        for r in rows:
            table = table_by_id.get(str(r.table_id))
            table_name = _trim(getattr(table, "name", "")) if table else ""
            table_key = _trim(getattr(table, "table_key", "")) if table else ""
            row_text = _render_table_row_text(getattr(r, "data_json", None))
            title = f"{table_name or '表格'} · 行 {int(getattr(r, 'row_index', 0)) + 1}"
            body = "\n\n".join([x for x in [table_name, table_key, row_text] if x]).strip()
            if not body:
                continue
            out.append(
                SearchDocInput(
                    source_type="project_table_row",
                    source_id=str(r.id),
                    title=title,
                    content=body,
                    url_path=f"/projects/{pid}/numeric-tables",
                    locator_json=json.dumps(
                        {
                            "table_id": str(getattr(r, "table_id", "") or "").strip(),
                            "table_key": table_key or None,
                            "row_id": str(r.id),
                            "row_index": int(getattr(r, "row_index", 0) or 0),
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    entity_name_by_id: dict[str, str] = {}
    if _has_table(db, name="entities"):
        entities = (
            db.execute(
                select(MemoryEntity)
                .where(MemoryEntity.project_id == pid, MemoryEntity.deleted_at.is_(None))
                .order_by(MemoryEntity.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for e in entities:
            name = _trim(getattr(e, "name", "")) or str(e.id)
            entity_name_by_id[str(e.id)] = name
            entity_type = _trim(getattr(e, "entity_type", "")) or "entity"
            summary = _trim(getattr(e, "summary_md", ""))
            attrs = _trim(getattr(e, "attributes_json", ""))
            body = "\n\n".join([x for x in [name, summary, attrs] if x]).strip()
            out.append(
                SearchDocInput(
                    source_type="memory_entity",
                    source_id=str(e.id),
                    title=f"[{entity_type}] {name}".strip(),
                    content=body or name,
                    url_path=f"/projects/{pid}/structured-memory",
                    locator_json=json.dumps({"table": "entities", "entity_id": str(e.id)}, ensure_ascii=False),
                )
            )

    if _has_table(db, name="relations"):
        relations = (
            db.execute(
                select(MemoryRelation)
                .where(MemoryRelation.project_id == pid, MemoryRelation.deleted_at.is_(None))
                .order_by(MemoryRelation.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for rel in relations:
            from_id = str(getattr(rel, "from_entity_id", "") or "").strip()
            to_id = str(getattr(rel, "to_entity_id", "") or "").strip()
            from_name = entity_name_by_id.get(from_id, from_id or "unknown")
            to_name = entity_name_by_id.get(to_id, to_id or "unknown")
            rel_type = _trim(getattr(rel, "relation_type", "")) or "related_to"
            title = f"{from_name} --({rel_type})→ {to_name}"
            desc = _trim(getattr(rel, "description_md", ""))
            attrs = _trim(getattr(rel, "attributes_json", ""))
            body = "\n\n".join([x for x in [title, desc, attrs] if x]).strip()
            out.append(
                SearchDocInput(
                    source_type="memory_relation",
                    source_id=str(rel.id),
                    title=title,
                    content=body or title,
                    url_path=f"/projects/{pid}/structured-memory?view=character-relations&relationId={str(rel.id)}",
                    locator_json=json.dumps(
                        {
                            "relation_id": str(rel.id),
                            "from_entity_id": from_id or None,
                            "to_entity_id": to_id or None,
                            "relation_type": rel_type,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    if _has_table(db, name="evidence"):
        evidence_rows = (
            db.execute(
                select(MemoryEvidence)
                .where(MemoryEvidence.project_id == pid, MemoryEvidence.deleted_at.is_(None))
                .order_by(MemoryEvidence.created_at.desc())
            )
            .scalars()
            .all()
        )
        for ev in evidence_rows:
            src_type = _trim(getattr(ev, "source_type", "")) or "unknown"
            src_id = _trim(getattr(ev, "source_id", ""))
            title = f"证据：{src_type}{(':' + src_id) if src_id else ''}"
            quote = _trim(getattr(ev, "quote_md", ""))
            attrs = _trim(getattr(ev, "attributes_json", ""))
            body = "\n\n".join([x for x in [title, quote, attrs] if x]).strip()
            out.append(
                SearchDocInput(
                    source_type="memory_evidence",
                    source_id=str(ev.id),
                    title=title,
                    content=body or title,
                    url_path=f"/projects/{pid}/structured-memory",
                    locator_json=json.dumps(
                        {
                            "evidence_id": str(ev.id),
                            "source_type": src_type,
                            "source_id": src_id or None,
                        },
                        ensure_ascii=False,
                    ),
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


def _split_query_terms(q: str) -> list[str]:
    q_norm = (q or "").strip()
    if not q_norm:
        return []
    parts = [p.strip() for p in re.split(r"\s+", q_norm) if p.strip()]
    return parts[:_MAX_QUERY_TERMS]


def _fts_query_fuzzy(q: str) -> str:
    parts = _split_query_terms(q)
    if not parts:
        return ""

    def render_term(t: str) -> str:
        t_norm = (t or "").strip()
        if not t_norm:
            return ""
        if _SAFE_FTS_TERM_RE.match(t_norm) and len(t_norm) >= 2:
            return f"{t_norm}*"
        return _fts_query_literal(t_norm)

    rendered = [render_term(p) for p in parts]
    rendered = [x for x in rendered if x]
    return " ".join(rendered).strip()


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
        fts_q = _fts_query_fuzzy(q_raw)
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
            "d.locator_json AS locator_json,"
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
                "locator_json": (str(r[5] or "").strip() or None),
            }
            for r in rows
        ]
        next_offset = (offset + limit) if len(items) >= limit else None
        return {"items": items, "next_offset": next_offset, "mode": "fts", "fts_enabled": True}

    # Fallback: LIKE on normalized documents. Lower quality but keeps the UI usable.
    terms = _split_query_terms(q_raw)
    if not terms:
        return {"items": [], "next_offset": None, "mode": "empty", "fts_enabled": False}
    params["q_primary"] = terms[0]

    dialect = str(getattr(getattr(db.get_bind(), "dialect", None), "name", "") or "")
    like_op = "ILIKE" if dialect == "postgresql" else "LIKE"
    pos_fn = "strpos" if dialect == "postgresql" else "instr"

    where_parts: list[str] = []
    for idx, term in enumerate(terms):
        k = f"term_{idx}"
        params[k] = f"%{term}%"
        where_parts.append(f"(COALESCE(title,'') {like_op} :{k} OR content {like_op} :{k})")
    where = f"project_id = :project_id AND ({' AND '.join(where_parts)})"
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
                "SELECT source_type,source_id,COALESCE(title,'') AS title,content, url_path, locator_json, "
                f"CASE WHEN COALESCE(title,'') {like_op} :term_0 THEN 0 ELSE 1 END AS title_hit, "
                f"CASE WHEN content {like_op} :term_0 THEN 0 ELSE 1 END AS content_hit, "
                f"{pos_fn}(lower(COALESCE(title,'')), lower(:q_primary)) AS title_pos, "
                f"{pos_fn}(lower(content), lower(:q_primary)) AS content_pos "
                "FROM search_documents "
                f"WHERE {where} "
                "ORDER BY title_hit ASC, content_hit ASC, "
                "CASE WHEN title_pos > 0 THEN title_pos ELSE 999999 END ASC, "
                "CASE WHEN content_pos > 0 THEN content_pos ELSE 999999 END ASC, "
                "updated_at DESC, id DESC "
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
            "snippet": _like_snippet(content=str(r[3] or ""), q=str(params.get("q_primary") or "")),
            "jump_url": (str(r[4] or "").strip() or None),
            "locator_json": (str(r[5] or "").strip() or None),
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
        running = (
            db.execute(
                select(ProjectTask)
                .where(
                    ProjectTask.project_id == pid,
                    ProjectTask.kind == "search_rebuild",
                    ProjectTask.status == "running",
                )
                .order_by(ProjectTask.started_at.desc(), ProjectTask.created_at.desc(), ProjectTask.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        # If a rebuild is already running, changes may happen while it is executing (especially with async inline queue).
        # Schedule a follow-up rebuild so the index eventually converges to the latest project state.
        if running is not None:
            idempotency_key = f"search:project:after:{running.id}:v1"
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

            created_task = False
            if task is None:
                created_task = True
                task = ProjectTask(
                    id=new_id(),
                    project_id=pid,
                    actor_user_id=actor_user_id,
                    kind="search_rebuild",
                    status="queued",
                    idempotency_key=idempotency_key,
                    params_json=json.dumps(
                        {
                            "reason": reason_norm,
                            "request_id": request_id,
                            "triggered_at": utc_now().isoformat().replace("+00:00", "Z"),
                            "after_task_id": str(running.id),
                        },
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
                event_type = None
                if status_norm not in {"queued", "running"}:
                    reset_project_task_to_queued(task=task, increment_retry_count=status_norm == "failed")
                    db.commit()
                    event_type = "retry" if status_norm == "failed" else "queued"
                else:
                    event_type = None

            return emit_and_enqueue_project_task(
                db,
                task=task,
                request_id=request_id,
                logger=logger,
                event_type=("queued" if created_task else event_type),
                source="scheduler",
                payload={"reason": reason_norm, "request_id": request_id, "after_task_id": str(running.id)},
            )

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

        created_task = False
        if task is None:
            created_task = True
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
            event_type = None
            if status_norm not in {"queued", "running"}:
                reset_project_task_to_queued(task=task, increment_retry_count=status_norm == "failed")
                db.commit()
                event_type = "retry" if status_norm == "failed" else "queued"
            else:
                event_type = None
        return emit_and_enqueue_project_task(
            db,
            task=task,
            request_id=request_id,
            logger=logger,
            event_type=("queued" if created_task else event_type),
            source="scheduler",
            payload={"reason": reason_norm, "request_id": request_id},
        )
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
