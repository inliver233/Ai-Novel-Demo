from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session, load_only

from app.core.config import settings
from app.core.logging import exception_log_fields, log_event
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryRelation

logger = logging.getLogger("ainovel")

_PROMPT_BLOCK_CHAR_LIMIT = 6000
_PROMPT_BLOCK_TRUNCATION_MARK = "\n…(truncated)\n"
_MATCH_ENTITY_ALIAS_CANDIDATES_LIMIT = 2000


def _build_prompt_block(*, inner: str, char_limit: int) -> dict[str, Any]:
    prefix = "<GraphContext>\n"
    suffix = "\n</GraphContext>"

    if not inner.strip():
        return {
            "identifier": "sys.memory.graph_context",
            "role": "system",
            "text_md": "",
            "truncated": False,
            "char_limit": int(char_limit),
            "original_chars": 0,
        }

    raw_text = f"{prefix}{inner}{suffix}"
    original_chars = len(raw_text)

    if char_limit <= 0 or original_chars <= char_limit:
        return {
            "identifier": "sys.memory.graph_context",
            "role": "system",
            "text_md": raw_text,
            "truncated": False,
            "char_limit": int(char_limit),
            "original_chars": original_chars,
        }

    budget = max(0, int(char_limit) - len(prefix) - len(suffix))
    if budget <= 0:
        return {
            "identifier": "sys.memory.graph_context",
            "role": "system",
            "text_md": "",
            "truncated": True,
            "char_limit": int(char_limit),
            "original_chars": original_chars,
        }

    marker = _PROMPT_BLOCK_TRUNCATION_MARK
    if budget <= len(marker):
        clipped_inner = marker[:budget]
    else:
        clipped_inner = inner[: max(0, budget - len(marker))].rstrip() + marker
    clipped_text = f"{prefix}{clipped_inner}{suffix}"
    if len(clipped_text) > char_limit:
        clipped_text = clipped_text[:char_limit]
    return {
        "identifier": "sys.memory.graph_context",
        "role": "system",
        "text_md": clipped_text,
        "truncated": True,
        "char_limit": int(char_limit),
        "original_chars": original_chars,
    }


def _safe_json_loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_aliases(attrs: dict[str, Any]) -> list[str]:
    out: list[str] = []
    aliases = attrs.get("aliases")
    if isinstance(aliases, list):
        for a in aliases:
            if not isinstance(a, str):
                continue
            s = a.strip()
            if s:
                out.append(s)
    alias = attrs.get("alias")
    if isinstance(alias, str):
        s = alias.strip()
        if s:
            out.append(s)
    aka = attrs.get("aka")
    if isinstance(aka, list):
        for a in aka:
            if not isinstance(a, str):
                continue
            s = a.strip()
            if s:
                out.append(s)
    return out


def _match_entities(*, entities: list[MemoryEntity], query_text: str, max_matches: int) -> list[tuple[str, str]]:
    q = (query_text or "").strip().lower()
    if not q:
        return []

    scored: list[tuple[tuple[int, int], str, str]] = []
    for e in entities:
        name = str(e.name or "").strip()
        if not name:
            continue
        attrs = _safe_json_loads_dict(e.attributes_json)
        candidates = [name, *_extract_aliases(attrs)]
        best: tuple[int, int] | None = None
        for cand in candidates:
            s = str(cand or "").strip()
            if len(s) < 2:
                continue
            idx = q.find(s.lower())
            if idx < 0:
                continue
            key = (idx, -len(s))
            if best is None or key < best:
                best = key
        if best is None:
            continue
        scored.append((best, str(e.id), name))

    scored.sort(key=lambda t: t[0])
    picked = scored[: max(0, int(max_matches))]
    return [(eid, name) for _score, eid, name in picked]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _extract_query_phrases(query_text: str, *, max_phrases: int = 48, max_ngram: int = 4) -> list[str]:
    raw = (query_text or "").strip()
    if not raw:
        return []

    tokens = [
        t.strip().lower()
        for t in re.findall(r"[0-9A-Za-z\u4e00-\u9fff][0-9A-Za-z\u4e00-\u9fff_-]*", raw)
        if t.strip()
    ]
    tokens = [t for t in tokens if len(t) >= 2]

    # De-dup while preserving order.
    uniq_tokens: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        uniq_tokens.append(t)
        if len(uniq_tokens) >= max_phrases:
            return uniq_tokens

    phrases: list[str] = list(uniq_tokens)
    if len(phrases) >= max_phrases:
        return phrases[:max_phrases]

    n_tokens = len(uniq_tokens)
    max_n = min(int(max_ngram), n_tokens)
    for n in range(2, max_n + 1):
        for i in range(0, n_tokens - n + 1):
            phrase = " ".join(uniq_tokens[i : i + n]).strip()
            if len(phrase) < 2 or phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)
            if len(phrases) >= max_phrases:
                return phrases

    return phrases


def _load_match_candidates(
    *,
    db: Session,
    project_id: str,
    query_text: str,
    alias_candidates_limit: int,
) -> tuple[list[MemoryEntity], dict[str, Any]]:
    q = (query_text or "").strip()
    if not q:
        return [], {"loaded": 0, "name_loaded": 0, "alias_loaded": 0, "alias_truncated": False}

    base = (
        select(MemoryEntity)
        .options(load_only(MemoryEntity.id, MemoryEntity.name, MemoryEntity.attributes_json))
        .where(MemoryEntity.project_id == project_id)
        .where(MemoryEntity.deleted_at.is_(None))
    )

    q_expr = func.lower(literal(q))
    name_candidates = (
        db.execute(base.where(q_expr.contains(func.lower(MemoryEntity.name))).order_by(MemoryEntity.updated_at.desc()))
        .scalars()
        .all()
    )
    name_ids = {str(e.id) for e in name_candidates}

    alias_candidates: list[MemoryEntity] = []
    alias_truncated = False
    phrases = _extract_query_phrases(q)
    if phrases and int(alias_candidates_limit) > 0:
        attr_lower = func.lower(MemoryEntity.attributes_json)
        like_exprs = [attr_lower.like(f"%{_escape_like(p)}%", escape="\\") for p in phrases]
        stmt = base.where(and_(MemoryEntity.attributes_json.is_not(None), or_(*like_exprs)))
        if name_ids:
            stmt = stmt.where(MemoryEntity.id.notin_(name_ids))

        # Fetch one extra row to detect truncation without running COUNT(*).
        limit_plus_one = int(alias_candidates_limit) + 1
        alias_candidates = (
            db.execute(stmt.order_by(MemoryEntity.updated_at.desc()).limit(limit_plus_one)).scalars().all()
        )
        if len(alias_candidates) > int(alias_candidates_limit):
            alias_truncated = True
            alias_candidates = alias_candidates[: int(alias_candidates_limit)]

    candidates = [*name_candidates, *alias_candidates]
    meta = {
        "loaded": len(candidates),
        "name_loaded": len(name_candidates),
        "alias_loaded": len(alias_candidates),
        "alias_limit": int(alias_candidates_limit),
        "alias_truncated": bool(alias_truncated),
        "phrases": len(phrases),
    }
    return candidates, meta


def query_graph_context(
    *,
    db: Session,
    project_id: str,
    query_text: str,
    hop: int = 1,
    max_nodes: int = 40,
    max_edges: int = 120,
    enabled: bool = True,
) -> dict[str, Any]:
    """
    Phase 6.1: GraphContext (1-hop) from structured memory tables.

    Fail-soft: returns stable shape even when empty / disabled / errors.
    """
    if not enabled:
        return {
            "enabled": False,
            "disabled_reason": "disabled",
            "query_text": query_text,
            "params": {"hop": int(hop), "max_nodes": int(max_nodes), "max_edges": int(max_edges)},
            "matched": {"entity_ids": [], "entity_names": []},
            "nodes": [],
            "edges": [],
            "evidence": [],
            "timings_ms": {},
            "truncated": {"nodes": False, "edges": False},
            "prompt_block": _build_prompt_block(inner="", char_limit=_PROMPT_BLOCK_CHAR_LIMIT),
            "logs": [],
        }

    t0 = time.perf_counter()
    try:
        effective_query_text = query_text
        if bool(getattr(settings, "glossary_query_expand_enabled", False)):
            try:
                from app.services.glossary_service import expand_query_text_with_glossary

                effective_query_text, _obs = expand_query_text_with_glossary(
                    db=db,
                    project_id=project_id,
                    query_text=query_text,
                )
            except Exception:
                effective_query_text = query_text

        hop = max(0, min(int(hop), 1))
        max_nodes = max(1, min(int(max_nodes), 200))
        max_edges = max(0, min(int(max_edges), 500))

        candidates, match_meta = _load_match_candidates(
            db=db,
            project_id=project_id,
            query_text=effective_query_text,
            alias_candidates_limit=_MATCH_ENTITY_ALIAS_CANDIDATES_LIMIT,
        )

        matched_pairs = _match_entities(entities=candidates, query_text=effective_query_text, max_matches=min(12, max_nodes))
        seed_ids = [eid for eid, _name in matched_pairs]
        seed_set = set(seed_ids)
        matched_names = [_name for _eid, _name in matched_pairs]

        node_ids: set[str] = set(seed_ids)
        picked_edges: list[MemoryRelation] = []
        truncated_edges = False
        truncated_nodes = False

        if hop >= 1 and seed_ids and max_edges > 0:
            rels = (
                db.execute(
                    select(MemoryRelation)
                    .where(MemoryRelation.project_id == project_id)
                    .where(MemoryRelation.deleted_at.is_(None))
                    .where(or_(MemoryRelation.from_entity_id.in_(seed_ids), MemoryRelation.to_entity_id.in_(seed_ids)))
                    .order_by(
                        MemoryRelation.updated_at.desc(),
                        MemoryRelation.relation_type.asc(),
                        MemoryRelation.from_entity_id.asc(),
                        MemoryRelation.to_entity_id.asc(),
                        MemoryRelation.id.asc(),
                    )
                )
                .scalars()
                .all()
            )

            for r in rels:
                if len(picked_edges) >= max_edges:
                    truncated_edges = True
                    break
                a = str(r.from_entity_id)
                b = str(r.to_entity_id)
                if a not in seed_set and b not in seed_set:
                    continue
                new_nodes = [x for x in (a, b) if x not in node_ids]
                if len(node_ids) + len(new_nodes) > max_nodes:
                    truncated_nodes = True
                    continue
                node_ids.update(new_nodes)
                picked_edges.append(r)

        nodes: list[MemoryEntity] = []
        if node_ids:
            nodes = (
                db.execute(
                    select(MemoryEntity)
                    .where(MemoryEntity.project_id == project_id)
                    .where(MemoryEntity.deleted_at.is_(None))
                    .where(MemoryEntity.id.in_(list(node_ids)))
                )
                .scalars()
                .all()
            )

        evidence_source_ids: list[str] = [*node_ids, *[str(e.id) for e in picked_edges]]
        evidence = (
            db.execute(
                select(MemoryEvidence)
                .where(MemoryEvidence.project_id == project_id)
                .where(MemoryEvidence.deleted_at.is_(None))
                .where(MemoryEvidence.source_id.is_not(None))
                .where(MemoryEvidence.source_id.in_(evidence_source_ids))
                .order_by(
                    MemoryEvidence.created_at.desc(),
                    func.coalesce(MemoryEvidence.source_type, "").asc(),
                    MemoryEvidence.source_id.asc(),
                    MemoryEvidence.id.asc(),
                )
                .limit(200)
            )
            .scalars()
            .all()
        )

        t1 = time.perf_counter()

        id_to_name = {str(e.id): str(e.name or "") for e in nodes}
        node_payloads: list[dict[str, Any]] = []
        for e in nodes:
            attrs = _safe_json_loads_dict(e.attributes_json)
            node_payloads.append(
                {
                    "id": str(e.id),
                    "entity_type": str(e.entity_type or "generic"),
                    "name": str(e.name or ""),
                    "summary_md": e.summary_md,
                    "attributes": attrs,
                    "matched": str(e.id) in seed_set,
                }
            )

        node_payloads.sort(
            key=lambda n: (
                not bool(n.get("matched")),
                str(n.get("entity_type") or ""),
                str(n.get("name") or "").lower(),
                str(n.get("id") or ""),
            )
        )

        edge_payloads: list[dict[str, Any]] = []
        for r in picked_edges:
            edge_payloads.append(
                {
                    "id": str(r.id),
                    "from_entity_id": str(r.from_entity_id),
                    "to_entity_id": str(r.to_entity_id),
                    "from_name": id_to_name.get(str(r.from_entity_id), ""),
                    "to_name": id_to_name.get(str(r.to_entity_id), ""),
                    "relation_type": str(r.relation_type or "related_to"),
                    "description_md": r.description_md,
                    "attributes": _safe_json_loads_dict(r.attributes_json),
                }
            )

        edge_payloads.sort(
            key=lambda e: (
                str(e.get("relation_type") or "related_to"),
                str(e.get("from_name") or e.get("from_entity_id") or ""),
                str(e.get("to_name") or e.get("to_entity_id") or ""),
                str(e.get("id") or ""),
            )
        )

        evidence_payloads: list[dict[str, Any]] = []
        for ev in evidence:
            evidence_payloads.append(
                {
                    "id": str(ev.id),
                    "source_type": str(ev.source_type or "unknown"),
                    "source_id": ev.source_id,
                    "quote_md": str(ev.quote_md or ""),
                    "attributes": _safe_json_loads_dict(ev.attributes_json),
                    "created_at": ev.created_at.isoformat().replace("+00:00", "Z"),
                }
            )

        lines: list[str] = []
        if matched_pairs:
            lines.append("Matched: " + ", ".join(matched_names))
        if node_payloads:
            lines.append("Nodes:")
            for n in node_payloads[: min(len(node_payloads), 30)]:
                mark = "★" if n.get("matched") else "-"
                lines.append(f"{mark} [{n.get('entity_type')}] {n.get('name')}".strip())
        if edge_payloads:
            lines.append("Edges:")
            for e in edge_payloads[: min(len(edge_payloads), 60)]:
                a = str(e.get("from_name") or e.get("from_entity_id") or "")
                b = str(e.get("to_name") or e.get("to_entity_id") or "")
                rt = str(e.get("relation_type") or "related_to")
                desc = str(e.get("description_md") or "").strip()
                line = f"- {a} --({rt})-> {b}"
                if desc:
                    line += f": {desc}"
                lines.append(line)

        inner = "\n".join(lines).strip()
        prompt_block = _build_prompt_block(inner=inner, char_limit=_PROMPT_BLOCK_CHAR_LIMIT)

        out = {
            "enabled": True,
            "disabled_reason": None,
            "query_text": query_text,
            "params": {"hop": hop, "max_nodes": max_nodes, "max_edges": max_edges},
            "matched": {"entity_ids": seed_ids, "entity_names": matched_names},
            "nodes": node_payloads,
            "edges": edge_payloads,
            "evidence": evidence_payloads,
            "timings_ms": {"load": int((t1 - t0) * 1000), "format": int((time.perf_counter() - t1) * 1000)},
            "truncated": {"nodes": bool(truncated_nodes), "edges": bool(truncated_edges)},
            "prompt_block": prompt_block,
            "logs": [
                {
                    "section": "graph",
                    "matched_entity_ids": seed_ids[:5],
                    "match_candidates": match_meta,
                    "counts": {"nodes": len(node_payloads), "edges": len(edge_payloads), "evidence": len(evidence_payloads)},
                    "truncated": {"nodes": bool(truncated_nodes), "edges": bool(truncated_edges)},
                    "prompt_block_truncated": bool(prompt_block.get("truncated")),
                }
            ],
        }

        log_event(
            logger,
            "info",
            event="GRAPH_CONTEXT",
            action="query",
            project_id=project_id,
            query_chars=len(query_text or ""),
            matched_entity_ids=seed_ids[:8],
            counts=out["logs"][0]["counts"],
            truncated=out["logs"][0]["truncated"],
            timings_ms=out["timings_ms"],
        )
        return out
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="GRAPH_CONTEXT",
            action="query",
            project_id=project_id,
            **exception_log_fields(exc),
        )
        safe_error = f"graph_query_failed:{type(exc).__name__}"
        return {
            "enabled": False,
            "disabled_reason": "error",
            "error": safe_error,
            "query_text": query_text,
            "params": {"hop": int(hop), "max_nodes": int(max_nodes), "max_edges": int(max_edges)},
            "matched": {"entity_ids": [], "entity_names": []},
            "nodes": [],
            "edges": [],
            "evidence": [],
            "timings_ms": {"total": int((time.perf_counter() - t0) * 1000)},
            "truncated": {"nodes": False, "edges": False},
            "prompt_block": _build_prompt_block(inner="", char_limit=_PROMPT_BLOCK_CHAR_LIMIT),
            "logs": [],
        }
