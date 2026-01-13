from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.story_memory import StoryMemory
from app.models.structured_memory import MemoryEntity, MemoryEvent, MemoryForeshadow, MemoryRelation
from app.schemas.memory_pack import MemoryContextPackOut
from app.services.fractal_memory_service import get_fractal_context
from app.services.graph_context_service import query_graph_context
from app.services.vector_rag_service import vector_rag_status
from app.services.worldbook_service import preview_worldbook_trigger


_MEMORY_TEXT_MD_CHAR_LIMIT = 6000
_TRUNCATION_MARK = "\n…(truncated)\n"


def _wrap_and_truncate_block(*, tag: str, inner: str, char_limit: int) -> tuple[str, bool]:
    prefix = f"<{tag}>\n"
    suffix = f"\n</{tag}>"

    body = (inner or "").strip()
    if not body:
        return "", False

    raw = f"{prefix}{body}{suffix}"
    if char_limit <= 0 or len(raw) <= char_limit:
        return raw, False

    budget = max(0, int(char_limit) - len(prefix) - len(suffix))
    if budget <= 0:
        return "", True

    marker = _TRUNCATION_MARK
    if budget <= len(marker):
        clipped_inner = marker[:budget]
    else:
        clipped_inner = body[: max(0, budget - len(marker))].rstrip() + marker
    clipped = f"{prefix}{clipped_inner}{suffix}"
    if len(clipped) > char_limit:
        clipped = clipped[:char_limit]
    return clipped, True


def _format_story_memory_text_md(*, memories: list[StoryMemory], char_limit: int) -> tuple[str, bool]:
    parts: list[str] = []
    for m in memories:
        mem_type = str(m.memory_type or "").strip() or "memory"
        title = str(m.title or "").strip() or "Untitled"
        content = str(m.content or "").strip()
        if len(content) > 800:
            content = content[:800].rstrip() + "…"
        parts.append(f"### [{mem_type}] {title}\n{content}".rstrip())
    return _wrap_and_truncate_block(tag="StoryMemory", inner="\n\n".join(parts), char_limit=char_limit)


def _extract_query_tokens(query_text: str, *, limit: int) -> list[str]:
    q = (query_text or "").strip()
    if not q:
        return []
    tokens = [t.strip() for t in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", q) if t and t.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 2:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= int(limit):
            break
    return out


def _format_structured_text_md(
    *,
    entities: list[MemoryEntity],
    relations: list[dict[str, Any]],
    events: list[MemoryEvent],
    foreshadows: list[MemoryForeshadow],
    char_limit: int,
) -> tuple[str, bool]:
    sections: list[str] = []
    if entities:
        lines = []
        for e in entities:
            name = str(e.name or "").strip()
            if not name:
                continue
            entity_type = str(e.entity_type or "").strip() or "generic"
            summary = str(e.summary_md or "").strip()
            if len(summary) > 300:
                summary = summary[:300].rstrip() + "…"
            lines.append(f"- [{entity_type}] {name}{f': {summary}' if summary else ''}".rstrip())
        if lines:
            sections.append("## Entities\n" + "\n".join(lines))
    if relations:
        lines = []
        for r in relations:
            from_name = str(r.get("from_name") or "").strip() or str(r.get("from_entity_id") or "")
            to_name = str(r.get("to_name") or "").strip() or str(r.get("to_entity_id") or "")
            rel_type = str(r.get("relation_type") or "").strip() or "related_to"
            desc = str(r.get("description_md") or "").strip()
            if len(desc) > 240:
                desc = desc[:240].rstrip() + "…"
            lines.append(f"- {from_name} --({rel_type})--> {to_name}{f': {desc}' if desc else ''}".rstrip())
        if lines:
            sections.append("## Relations\n" + "\n".join(lines))
    if events:
        lines = []
        for ev in events:
            title = str(ev.title or "").strip() or "Untitled"
            content = str(ev.content_md or "").strip()
            if len(content) > 320:
                content = content[:320].rstrip() + "…"
            lines.append(f"- {title}{f': {content}' if content else ''}".rstrip())
        if lines:
            sections.append("## Events\n" + "\n".join(lines))
    if foreshadows:
        lines = []
        for f in foreshadows:
            title = str(f.title or "").strip() or "Untitled"
            content = str(f.content_md or "").strip()
            if len(content) > 320:
                content = content[:320].rstrip() + "…"
            resolved = bool(getattr(f, "resolved", 0))
            lines.append(f"- {'[resolved] ' if resolved else ''}{title}{f': {content}' if content else ''}".rstrip())
        if lines:
            sections.append("## Foreshadows\n" + "\n".join(lines))

    return _wrap_and_truncate_block(tag="StructuredMemory", inner="\n\n".join(sections), char_limit=char_limit)


def retrieve_memory_context_pack(
    *,
    db: Session,
    project_id: str,
    query_text: str = "",
    include_deleted: bool = False,
) -> MemoryContextPackOut:
    """
    Must be safe when memory dependencies (vector DB / embeddings / etc.) are missing.
    """
    worldbook_preview = preview_worldbook_trigger(
        db=db,
        project_id=project_id,
        query_text=query_text,
        include_constant=True,
        enable_recursion=True,
        char_limit=12000,
    )

    worldbook = {**worldbook_preview.model_dump(), "enabled": True, "disabled_reason": None}
    if not isinstance(worldbook.get("text_md"), str):
        worldbook["text_md"] = str(worldbook_preview.text_md or "")

    story_memory: dict[str, Any] = {"enabled": False, "disabled_reason": "empty", "items": [], "text_md": ""}
    try:
        limit_plus_one = 41
        tokens = _extract_query_tokens(query_text, limit=6)
        stmt = (
            select(StoryMemory)
            .where(StoryMemory.project_id == project_id)
            .order_by(StoryMemory.importance_score.desc(), StoryMemory.updated_at.desc())
        )
        if tokens:
            conds = []
            for t in tokens:
                like_term = f"%{t}%"
                conds.append(StoryMemory.content.like(like_term))
                conds.append(StoryMemory.title.like(like_term))
            filtered = db.execute(stmt.where(or_(*conds)).limit(limit_plus_one)).scalars().all()
            rows = filtered if filtered else db.execute(stmt.limit(limit_plus_one)).scalars().all()
        else:
            rows = db.execute(stmt.limit(limit_plus_one)).scalars().all()
        truncated = len(rows) > (limit_plus_one - 1)
        rows = rows[: limit_plus_one - 1]
        enabled = bool(rows)
        items = []
        for m in rows[:20]:
            items.append(
                {
                    "id": m.id,
                    "chapter_id": m.chapter_id,
                    "memory_type": m.memory_type,
                    "title": m.title,
                    "importance_score": float(m.importance_score or 0.0),
                    "story_timeline": int(m.story_timeline or 0),
                    "is_foreshadow": bool(m.is_foreshadow),
                    "content_preview": (str(m.content or "").strip()[:200] + "…") if len(str(m.content or "").strip()) > 200 else str(m.content or "").strip(),
                }
            )
        text_md, text_truncated = _format_story_memory_text_md(memories=rows[:12], char_limit=_MEMORY_TEXT_MD_CHAR_LIMIT)
        story_memory = {
            "enabled": enabled,
            "disabled_reason": None if enabled else "empty",
            "query_text": query_text,
            "filter_tokens": tokens,
            "items": items,
            "truncated": bool(truncated or text_truncated),
            "text_md": text_md,
        }
    except Exception:
        story_memory = {"enabled": False, "disabled_reason": "error", "items": [], "text_md": "", "error": "story_memory_query_failed"}

    structured: dict[str, Any] = {"enabled": False, "disabled_reason": "empty", "counts": {}, "text_md": ""}
    try:
        entities_stmt = select(MemoryEntity).where(MemoryEntity.project_id == project_id)
        relations_stmt = select(MemoryRelation).where(MemoryRelation.project_id == project_id)
        events_stmt = select(MemoryEvent).where(MemoryEvent.project_id == project_id)
        foreshadows_stmt = select(MemoryForeshadow).where(MemoryForeshadow.project_id == project_id)

        if not include_deleted:
            entities_stmt = entities_stmt.where(MemoryEntity.deleted_at.is_(None))
            relations_stmt = relations_stmt.where(MemoryRelation.deleted_at.is_(None))
            events_stmt = events_stmt.where(MemoryEvent.deleted_at.is_(None))
            foreshadows_stmt = foreshadows_stmt.where(MemoryForeshadow.deleted_at.is_(None))

        entities = db.execute(entities_stmt.order_by(MemoryEntity.updated_at.desc()).limit(21)).scalars().all()
        relations = db.execute(relations_stmt.order_by(MemoryRelation.updated_at.desc()).limit(41)).scalars().all()
        events = db.execute(events_stmt.order_by(MemoryEvent.updated_at.desc()).limit(21)).scalars().all()
        foreshadows = db.execute(foreshadows_stmt.order_by(MemoryForeshadow.updated_at.desc()).limit(21)).scalars().all()
        enabled = bool(entities or relations or events or foreshadows)

        rel_entity_ids: set[str] = set()
        for r in relations[:40]:
            rel_entity_ids.add(str(r.from_entity_id))
            rel_entity_ids.add(str(r.to_entity_id))
        entity_name_rows = []
        if rel_entity_ids:
            entity_name_stmt = (
                select(MemoryEntity.id, MemoryEntity.name)
                .where(MemoryEntity.project_id == project_id)
                .where(MemoryEntity.id.in_(list(rel_entity_ids)))
            )
            if not include_deleted:
                entity_name_stmt = entity_name_stmt.where(MemoryEntity.deleted_at.is_(None))
            entity_name_rows = db.execute(entity_name_stmt).all()
        name_by_id = {str(eid): str(name or "") for eid, name in entity_name_rows}
        relations_preview = []
        for r in relations[:40]:
            relations_preview.append(
                {
                    "id": r.id,
                    "from_entity_id": r.from_entity_id,
                    "to_entity_id": r.to_entity_id,
                    "from_name": name_by_id.get(str(r.from_entity_id)) or "",
                    "to_name": name_by_id.get(str(r.to_entity_id)) or "",
                    "relation_type": r.relation_type,
                    "description_md": r.description_md,
                }
            )

        text_md, text_truncated = _format_structured_text_md(
            entities=entities[:20],
            relations=relations_preview,
            events=events[:20],
            foreshadows=foreshadows[:20],
            char_limit=_MEMORY_TEXT_MD_CHAR_LIMIT,
        )
        structured = {
            "enabled": enabled,
            "disabled_reason": None if enabled else "empty",
            "include_deleted": bool(include_deleted),
            "counts": {
                "entities": len(entities[:20]),
                "relations": len(relations[:40]),
                "events": len(events[:20]),
                "foreshadows": len(foreshadows[:20]),
            },
            "truncated": bool(len(entities) > 20 or len(relations) > 40 or len(events) > 20 or len(foreshadows) > 20 or text_truncated),
            "text_md": text_md,
        }
    except Exception:
        structured = {"enabled": False, "disabled_reason": "error", "counts": {}, "text_md": "", "error": "structured_query_failed"}

    graph = query_graph_context(db=db, project_id=project_id, query_text=query_text, enabled=True)
    if isinstance(graph, dict):
        pb = graph.get("prompt_block") if isinstance(graph.get("prompt_block"), dict) else {}
        graph["text_md"] = str(pb.get("text_md") or "")

    vector_rag = vector_rag_status(project_id=project_id)
    if isinstance(vector_rag, dict):
        vector_rag["query_text"] = query_text
        pb = vector_rag.get("prompt_block") if isinstance(vector_rag.get("prompt_block"), dict) else {}
        vector_rag["text_md"] = str(pb.get("text_md") or "")

    fractal = get_fractal_context(db=db, project_id=project_id, enabled=bool(getattr(settings, "fractal_enabled", True)))
    if isinstance(fractal, dict):
        pb = fractal.get("prompt_block") if isinstance(fractal.get("prompt_block"), dict) else {}
        fractal["text_md"] = str(pb.get("text_md") or "")

    logs: list[dict[str, Any]] = [
        {
            "section": "worldbook",
            "enabled": bool(worldbook.get("enabled")),
            "disabled_reason": worldbook.get("disabled_reason"),
            "note": "preview_worldbook_trigger",
        },
        {
            "section": "story_memory",
            "enabled": bool(story_memory.get("enabled")),
            "disabled_reason": story_memory.get("disabled_reason"),
            "note": "story_memories (top by importance)",
        },
        {
            "section": "structured",
            "enabled": bool(structured.get("enabled")),
            "disabled_reason": structured.get("disabled_reason"),
            "note": "entities/relations/events/foreshadows summary",
        },
        {
            "section": "vector_rag",
            "enabled": bool(vector_rag.get("enabled")),
            "disabled_reason": vector_rag.get("disabled_reason"),
            "note": "vector_rag_status (use /vector/query for retrieval)",
        },
        {
            "section": "graph",
            "enabled": bool(graph.get("enabled")),
            "disabled_reason": graph.get("disabled_reason"),
            "note": "graph_context_service.query_graph_context",
        },
        {
            "section": "fractal",
            "enabled": bool(fractal.get("enabled")),
            "disabled_reason": fractal.get("disabled_reason"),
            "note": "Phase 6.2: use /api/projects/{project_id}/fractal/rebuild to rebuild deterministically",
        },
    ]

    return MemoryContextPackOut.model_validate(
        {
            "worldbook": worldbook,
            "story_memory": story_memory,
            "structured": structured,
            "vector_rag": vector_rag,
            "graph": graph,
            "fractal": fractal,
            "logs": logs,
        }
    )


def placeholder_memory_retrieval_log(*, enabled: bool) -> dict[str, Any]:
    """
    Phase 0 placeholder for `memory_retrieval_log_json`.

    Spec reference: `长期记忆系统完整实现规划.md` §14.2.
    """
    return {
        "phase": "0.1",
        "enabled": bool(enabled),
        "query_text": "",
        "per_section": {},
        "budgets": {},
        "overfilter": {},
        "errors": [],
    }


def build_memory_retrieval_log_json(
    *,
    enabled: bool,
    query_text: str,
    pack: MemoryContextPackOut | None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    per_section: dict[str, Any] = {}
    if pack is not None:
        for item in pack.logs:
            per_section[str(item.section)] = item.model_dump()

    safe_errors = [str(e).strip() for e in (errors or []) if str(e).strip()]
    return {
        "phase": "1.0",
        "enabled": bool(enabled),
        "query_text": str(query_text or ""),
        "per_section": per_section,
        "budgets": {},
        "overfilter": {},
        "errors": safe_errors,
    }
