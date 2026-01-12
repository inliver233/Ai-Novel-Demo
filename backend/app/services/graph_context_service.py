from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryRelation

logger = logging.getLogger("ainovel")

_PROMPT_BLOCK_CHAR_LIMIT = 6000
_PROMPT_BLOCK_TRUNCATION_MARK = "\n…(truncated)\n"


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
        hop = max(0, min(int(hop), 1))
        max_nodes = max(1, min(int(max_nodes), 200))
        max_edges = max(0, min(int(max_edges), 500))

        entities = (
            db.execute(
                select(MemoryEntity)
                .where(MemoryEntity.project_id == project_id)
                .where(MemoryEntity.deleted_at.is_(None))
                .order_by(MemoryEntity.updated_at.desc())
            )
            .scalars()
            .all()
        )

        matched_pairs = _match_entities(entities=entities, query_text=query_text, max_matches=min(12, max_nodes))
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
                    .order_by(MemoryRelation.updated_at.desc())
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

        nodes = [e for e in entities if str(e.id) in node_ids]

        evidence_source_ids: list[str] = [*node_ids, *[str(e.id) for e in picked_edges]]
        evidence = (
            db.execute(
                select(MemoryEvidence)
                .where(MemoryEvidence.project_id == project_id)
                .where(MemoryEvidence.deleted_at.is_(None))
                .where(MemoryEvidence.source_id.is_not(None))
                .where(MemoryEvidence.source_id.in_(evidence_source_ids))
                .order_by(MemoryEvidence.created_at.desc())
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
            error=str(exc),
        )
        return {
            "enabled": False,
            "disabled_reason": "error",
            "error": str(exc),
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
