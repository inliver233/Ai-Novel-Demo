from __future__ import annotations

import json
import hashlib
import math
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal, engine
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.project_settings import ProjectSettings
from app.models.project_task import ProjectTask
from app.models.story_memory import StoryMemory
from app.models.worldbook_entry import WorldBookEntry
from app.services.context_budget_observability import build_budget_observability
from app.services.embedding_service import (
    embed_texts as embed_texts_with_providers,
    embedding_enabled_reason,
    resolve_embedding_config,
)
from app.services.rerank_service import rerank_candidates as rerank_candidates_with_providers

logger = logging.getLogger("ainovel")

VectorSource = Literal["worldbook", "outline", "chapter", "story_memory"]


@dataclass(frozen=True, slots=True)
class VectorChunk:
    id: str
    text: str
    metadata: dict[str, Any]


_ALL_SOURCES: list[VectorSource] = ["worldbook", "outline", "chapter", "story_memory"]
_PGVECTOR_TABLE = "vector_chunks"
_PGVECTOR_READY_CACHE: tuple[bool, float] | None = None
_PGVECTOR_READY_CACHE_TTL_SECONDS = 30.0
_VECTOR_DROPPED_REASON_EXPLAIN = {
    "duplicate_chunk": "同一 source/source_id/chunk_index 已存在于最终候选，避免重复注入。",
    "per_source_budget": "同一 source+source_id 的 chunk 数达到上限（vector_per_source_id_max_chunks）。",
    "budget": "达到最终注入 chunk 上限（vector_final_max_chunks）。",
}


def _is_postgres() -> bool:
    return getattr(getattr(engine, "dialect", None), "name", "") == "postgresql"


def _pgvector_ready() -> bool:
    global _PGVECTOR_READY_CACHE
    now = time.time()
    cached = _PGVECTOR_READY_CACHE
    if cached is not None and (now - cached[1]) < _PGVECTOR_READY_CACHE_TTL_SECONDS:
        return bool(cached[0])

    if not _is_postgres():
        _PGVECTOR_READY_CACHE = (False, now)
        return False

    ready = False
    try:
        with engine.connect() as conn:
            ext_installed = bool(conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar())
            if not ext_installed:
                ready = False
            else:
                table_exists = bool(
                    conn.execute(text("SELECT to_regclass('public.vector_chunks') IS NOT NULL")).scalar()
                )
                ready = bool(table_exists)
    except Exception:
        ready = False

    _PGVECTOR_READY_CACHE = (bool(ready), now)
    return bool(ready)


def _prefer_pgvector() -> bool:
    backend = str(getattr(settings, "vector_backend", "auto") or "auto").strip().lower()
    if backend == "chroma":
        return False
    if backend == "pgvector":
        return _pgvector_ready()
    return _pgvector_ready()


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def _rrf_contrib(rank: int | None, *, k: int) -> float:
    if rank is None or rank <= 0:
        return 0.0
    return 1.0 / (k + rank)


def _rrf_score(*, vector_rank: int | None, fts_rank: int | None, k: int) -> float:
    return _rrf_contrib(vector_rank, k=k) + _rrf_contrib(fts_rank, k=k)


_RERANK_TOKEN_RE = re.compile("[A-Za-z0-9\u4e00-\u9fff]+")


def _rerank_tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {t.lower() for t in _RERANK_TOKEN_RE.findall(text) if t.strip()}


def _rerank_score(*, method: str, query_text: str, candidate_text: str) -> float:
    qtext = (query_text or "").strip()
    if not qtext:
        return 0.0

    if method == "rapidfuzz_token_set_ratio":
        from rapidfuzz import fuzz  # type: ignore[import-not-found]

        return float(fuzz.token_set_ratio(qtext, candidate_text or "")) / 100.0

    q_tokens = _rerank_tokens(qtext)
    if not q_tokens:
        return 0.0
    c_tokens = _rerank_tokens(candidate_text or "")
    if not c_tokens:
        return 0.0
    return float(len(q_tokens & c_tokens)) / float(len(q_tokens))


def _rerank_candidates(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    method: str,
    top_k: int,
    hybrid_alpha: float | None = None,
    external: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return rerank_candidates_with_providers(
        query_text=query_text,
        candidates=candidates,
        method=method,
        top_k=top_k,
        hybrid_alpha=hybrid_alpha,
        external=external,
        score_fn=_rerank_score,
    )


def _vector_candidate_key(candidate: dict[str, Any]) -> tuple[str, str]:
    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    return (str(meta.get("source") or ""), str(meta.get("source_id") or ""))


def _vector_candidate_chunk_key(candidate: dict[str, Any]) -> tuple[str, str, int]:
    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    try:
        chunk_index = int(meta.get("chunk_index") or 0)
    except Exception:
        chunk_index = 0
    return (str(meta.get("source") or ""), str(meta.get("source_id") or ""), chunk_index)


def _normalize_kb_priority_group(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in ("normal", "high") else "normal"


def _merge_kb_candidates_rrf(
    *,
    kb_ids: list[str],
    per_kb_candidates: dict[str, list[dict[str, Any]]],
    kb_weights: dict[str, float],
    kb_orders: dict[str, int],
    rrf_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Merge multiple kb candidate lists using weighted RRF.

    Deterministic order:
      - score desc
      - kb_order asc
      - distance asc
      - id asc
    """

    merged_obs: dict[str, Any] = {"mode": "rrf", "kb_ids": list(kb_ids), "rrf_k": int(rrf_k)}
    if len(kb_ids) <= 1:
        only = kb_ids[0] if kb_ids else None
        merged = list(per_kb_candidates.get(str(only or "")) or []) if only else []
        merged_obs["mode"] = "single"
        merged_obs["candidate_count"] = int(len(merged))
        return merged, merged_obs

    scored: dict[str, dict[str, Any]] = {}
    for kid in kb_ids:
        cand_list = per_kb_candidates.get(kid) or []
        weight = float(kb_weights.get(kid, 1.0))
        kb_order = int(kb_orders.get(kid, 999))
        for rank, c in enumerate(cand_list, start=1):
            cid = str(c.get("id") or "")
            if not cid:
                continue
            contrib = float(weight) * _rrf_contrib(rank, k=rrf_k)
            dist = float(c.get("distance") or 0.0)
            entry = scored.get(cid)
            if entry is None:
                scored[cid] = {"candidate": c, "score": contrib, "distance": dist, "kb_order": kb_order, "id": cid}
            else:
                entry["score"] = float(entry.get("score") or 0.0) + contrib
                prev_dist = entry.get("distance")
                if prev_dist is None or dist < float(prev_dist):
                    entry["candidate"] = c
                    entry["distance"] = dist
                prev_order = entry.get("kb_order")
                entry["kb_order"] = min(int(prev_order) if prev_order is not None else kb_order, kb_order)
    merged = list(scored.values())
    merged.sort(
        key=lambda x: (
            -float(x.get("score") or 0.0),
            int(x.get("kb_order")) if x.get("kb_order") is not None else 999,
            float(x.get("distance")) if x.get("distance") is not None else 0.0,
            str(x.get("id") or ""),
        )
    )
    candidates = [dict(x.get("candidate") or {}) for x in merged]
    for c in candidates:
        c.pop("_rrf_score", None)

    merged_obs["candidate_count"] = int(len(candidates))
    return candidates, merged_obs


def _merge_kb_candidates(
    *,
    kb_ids: list[str],
    per_kb_candidates: dict[str, list[dict[str, Any]]],
    kb_weights: dict[str, float],
    kb_orders: dict[str, int],
    kb_priority_groups: dict[str, str],
    top_k: int,
    priority_enabled: bool,
    rrf_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not bool(priority_enabled):
        candidates, obs = _merge_kb_candidates_rrf(
            kb_ids=kb_ids,
            per_kb_candidates=per_kb_candidates,
            kb_weights=kb_weights,
            kb_orders=kb_orders,
            rrf_k=rrf_k,
        )
        obs["priority_enabled"] = False
        obs.setdefault("candidate_count", int(len(candidates)))
        return candidates, obs

    high_kb_ids = [kid for kid in kb_ids if kb_priority_groups.get(kid) == "high"]
    if not high_kb_ids:
        candidates, obs = _merge_kb_candidates_rrf(
            kb_ids=kb_ids,
            per_kb_candidates=per_kb_candidates,
            kb_weights=kb_weights,
            kb_orders=kb_orders,
            rrf_k=rrf_k,
        )
        obs["priority_enabled"] = True
        obs.setdefault("candidate_count", int(len(candidates)))
        obs.setdefault("note", "no_high_priority_kbs")
        return candidates, obs

    high_set = set(high_kb_ids)
    normal_kb_ids = [kid for kid in kb_ids if kid not in high_set]
    if not normal_kb_ids:
        candidates, obs = _merge_kb_candidates_rrf(
            kb_ids=kb_ids,
            per_kb_candidates=per_kb_candidates,
            kb_weights=kb_weights,
            kb_orders=kb_orders,
            rrf_k=rrf_k,
        )
        obs["priority_enabled"] = True
        obs.setdefault("candidate_count", int(len(candidates)))
        obs.setdefault("note", "only_high_priority_kbs")
        return candidates, obs

    high_candidates, high_obs = _merge_kb_candidates_rrf(
        kb_ids=high_kb_ids,
        per_kb_candidates=per_kb_candidates,
        kb_weights=kb_weights,
        kb_orders=kb_orders,
        rrf_k=rrf_k,
    )

    combined: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for c in high_candidates:
        cid = str(c.get("id") or "")
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)
        combined.append(c)
        if len(combined) >= int(top_k):
            break

    used_normal = False
    normal_obs: dict[str, Any] | None = None
    if len(combined) < int(top_k):
        used_normal = True
        normal_candidates, normal_obs = _merge_kb_candidates_rrf(
            kb_ids=normal_kb_ids,
            per_kb_candidates=per_kb_candidates,
            kb_weights=kb_weights,
            kb_orders=kb_orders,
            rrf_k=rrf_k,
        )
        for c in normal_candidates:
            cid = str(c.get("id") or "")
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            combined.append(c)
            if len(combined) >= int(top_k):
                break

    obs = {
        "mode": "priority",
        "priority_enabled": True,
        "rrf_k": int(rrf_k),
        "top_k": int(top_k),
        "groups": {"high": list(high_kb_ids), "normal": list(normal_kb_ids)},
        "high": high_obs,
        "normal": normal_obs,
        "used_normal": bool(used_normal),
        "candidate_count": int(len(combined)),
    }
    return combined, obs


def _parse_vector_source_order() -> list[str] | None:
    raw = str(getattr(settings, "vector_source_order", "") or "").strip()
    if not raw:
        return None
    parts = [p.strip().lower() for p in re.split(r"[\\s,|;]+", raw) if p.strip()]
    out: list[str] = []
    for p in parts:
        if p not in _ALL_SOURCES:
            continue
        if p in out:
            continue
        out.append(p)
    return out or None


def _parse_vector_source_weights() -> dict[str, float] | None:
    raw = str(getattr(settings, "vector_source_weights_json", "") or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    out: dict[str, float] = {}
    for k, v in value.items():
        source = str(k or "").strip().lower()
        if source not in _ALL_SOURCES:
            continue
        try:
            weight = float(v)
        except Exception:
            continue
        if weight <= 0:
            continue
        out[source] = weight
    return out or None


def _super_sort_final_chunks(
    final_chunks: list[dict[str, Any]], *, super_sort: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before_ids = [str(c.get("id") or "") for c in final_chunks if isinstance(c, dict)]

    requested = super_sort if isinstance(super_sort, dict) else None

    override_enabled: bool | None = None
    override_order: list[str] | None = None
    override_weights: dict[str, float] | None = None

    if requested is not None:
        if "enabled" in requested:
            override_enabled = bool(requested.get("enabled"))

        raw_order = requested.get("source_order")
        if isinstance(raw_order, str):
            parts = [p.strip().lower() for p in re.split(r"[\\s,|;]+", raw_order) if p.strip()]
        elif isinstance(raw_order, list):
            parts = [str(p or "").strip().lower() for p in raw_order if str(p or "").strip()]
        else:
            parts = []
        if parts:
            order: list[str] = []
            for p in parts:
                if p not in _ALL_SOURCES:
                    continue
                if p in order:
                    continue
                order.append(p)
            override_order = order or None

        raw_weights = requested.get("source_weights")
        if isinstance(raw_weights, dict):
            out: dict[str, float] = {}
            for k, v in raw_weights.items():
                source = str(k or "").strip().lower()
                if source not in _ALL_SOURCES:
                    continue
                try:
                    weight = float(v)
                except Exception:
                    continue
                if weight <= 0:
                    continue
                out[source] = weight
            override_weights = out or None

    order_cfg = override_order if override_order is not None else _parse_vector_source_order()
    weights_cfg = override_weights if override_weights is not None else _parse_vector_source_weights()
    enabled = bool(order_cfg or weights_cfg)
    if override_enabled is False:
        enabled = False

    base_obs: dict[str, Any] = {
        "enabled": bool(enabled),
        "applied": False,
        "reason": "disabled" if not enabled else None,
        "override_enabled": override_enabled,
        "requested": requested,
        "source_order": order_cfg,
        "source_weights": weights_cfg,
        "before": before_ids,
        "after": list(before_ids),
    }
    if not enabled or len(final_chunks) <= 1:
        if enabled:
            base_obs["reason"] = "noop"
        return list(final_chunks), base_obs

    if order_cfg:
        order = list(order_cfg)
        for s in _ALL_SOURCES:
            if s not in order:
                order.append(s)
    else:
        weights_for_sort = weights_cfg or {}
        order = sorted(_ALL_SOURCES, key=lambda s: (-float(weights_for_sort.get(s, 1.0)), s))

    weights_for_all = {s: float((weights_cfg or {}).get(s, 1.0)) for s in _ALL_SOURCES}
    order_index = {s: i for i, s in enumerate(order)}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for c in final_chunks:
        if not isinstance(c, dict):
            continue
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        source = str(meta.get("source") or "")
        grouped.setdefault(source, []).append(c)

    def _natural_key(source: str, c: dict[str, Any]) -> tuple:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        try:
            chunk_index = int(meta.get("chunk_index") or 0)
        except Exception:
            chunk_index = 0
        source_id = str(meta.get("source_id") or "")
        cid = str(c.get("id") or "")
        if source == "chapter":
            try:
                chapter_number = int(meta.get("chapter_number") or 0)
            except Exception:
                chapter_number = 0
            return (chapter_number, chunk_index, source_id, cid)
        title = str(meta.get("title") or "")
        return (title, chunk_index, source_id, cid)

    for source, items in grouped.items():
        items.sort(key=lambda c: _natural_key(source, c))

    pos = {s: 0 for s in grouped.keys()}
    taken = {s: 0 for s in grouped.keys()}

    out: list[dict[str, Any]] = []
    while True:
        available = [s for s in grouped.keys() if pos.get(s, 0) < len(grouped[s])]
        if not available:
            break

        def _pick_key(s: str) -> tuple[float, int, str]:
            weight = float(weights_for_all.get(s, 1.0))
            if weight <= 0:
                weight = 1.0
            ratio = float(taken.get(s, 0)) / weight
            return (ratio, int(order_index.get(s, 999)), s)

        selected_source = min(available, key=_pick_key)
        out.append(grouped[selected_source][pos[selected_source]])
        pos[selected_source] = int(pos.get(selected_source, 0)) + 1
        taken[selected_source] = int(taken.get(selected_source, 0)) + 1

    after_ids = [str(c.get("id") or "") for c in out if isinstance(c, dict)]
    obs = dict(base_obs)
    obs.update(
        {
            "applied": after_ids != before_ids,
            "reason": "ok",
            "source_order_effective": order,
            "source_weights_effective": weights_for_all,
            "after": after_ids,
            "by_source": {s: len(grouped[s]) for s in sorted(grouped.keys())},
        }
    )
    return out, obs


def _build_vector_query_counts(
    *,
    candidates_total: int,
    returned_candidates: list[dict[str, Any]],
    final_selected: int,
    dropped: list[dict[str, Any]],
) -> dict[str, Any]:
    unique_keys: set[tuple[str, str]] = set()
    for c in returned_candidates:
        if isinstance(c, dict):
            unique_keys.add(_vector_candidate_key(c))

    dropped_by_reason: dict[str, int] = {}
    for d in dropped:
        if not isinstance(d, dict):
            continue
        reason = str(d.get("reason") or "")
        if not reason:
            continue
        dropped_by_reason[reason] = dropped_by_reason.get(reason, 0) + 1

    return {
        "candidates_total": int(candidates_total),
        "candidates_returned": int(len(returned_candidates)),
        "unique_sources": int(len(unique_keys)),
        "final_selected": int(final_selected),
        "dropped_total": int(len(dropped)),
        "dropped_by_reason": dropped_by_reason,
    }


def _vector_budget_observability(
    *,
    top_k: int,
    max_chunks: int,
    per_source_max_chunks: int,
    char_limit: int,
    dropped: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_budget_observability(
        module="vector",
        limits={
            "max_candidates": int(top_k),
            "final_max_chunks": int(max_chunks),
            "per_source_max_chunks": int(per_source_max_chunks),
            "final_char_limit": int(char_limit),
        },
        dropped=dropped,
        reason_explain=_VECTOR_DROPPED_REASON_EXPLAIN,
    )


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_chroma_persist_dir() -> str:
    return str((_backend_dir() / ".chroma").resolve().as_posix())


def _vector_enabled_reason(*, embedding: dict[str, str | None] | None = None) -> tuple[bool, str | None]:
    config = resolve_embedding_config(embedding)
    return embedding_enabled_reason(config)


def _resolve_rerank_config(rerank: dict[str, Any] | None) -> tuple[bool, str, int, float]:
    enabled = bool(getattr(settings, "vector_rerank_enabled", False))
    method = "auto"
    top_k = int(getattr(settings, "vector_max_candidates", 20) or 20)
    hybrid_alpha = 0.0
    if rerank is None:
        return enabled, method, max(1, min(int(top_k), 1000)), float(hybrid_alpha)

    if "enabled" in rerank:
        enabled = bool(rerank.get("enabled"))
    raw_method = str(rerank.get("method") or "").strip()
    if raw_method:
        method = raw_method

    provider_raw = str(rerank.get("provider") or "").strip()
    if method == "auto" and provider_raw == "external_rerank_api":
        method = "external_rerank_api"
    if "top_k" in rerank and rerank.get("top_k") is not None:
        try:
            top_k = int(rerank.get("top_k"))
        except Exception:
            pass
    if "hybrid_alpha" in rerank and rerank.get("hybrid_alpha") is not None:
        try:
            hybrid_alpha = float(rerank.get("hybrid_alpha"))
        except Exception:
            hybrid_alpha = 0.0
    hybrid_alpha = max(0.0, min(float(hybrid_alpha), 1.0))
    return enabled, method, max(1, min(int(top_k), 1000)), float(hybrid_alpha)


def _resolve_rerank_external_config(rerank: dict[str, Any] | None) -> dict[str, Any] | None:
    if rerank is None:
        return None
    if not isinstance(rerank, dict):
        return None

    out: dict[str, Any] = {}

    base_url = str(rerank.get("base_url") or "").strip()
    if base_url:
        out["base_url"] = base_url

    model = str(rerank.get("model") or "").strip()
    if model:
        out["model"] = model

    api_key = str(rerank.get("api_key") or "").strip()
    if api_key:
        out["api_key"] = api_key

    timeout_seconds = rerank.get("timeout_seconds")
    if timeout_seconds is not None:
        out["timeout_seconds"] = timeout_seconds

    return out or None


def vector_rag_status(
    *,
    project_id: str,
    sources: list[VectorSource] | None = None,
    embedding: dict[str, str | None] | None = None,
    rerank: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = sources or list(_ALL_SOURCES)
    enabled, disabled_reason = _vector_enabled_reason(embedding=embedding)
    rerank_enabled, rerank_method, rerank_top_k, rerank_hybrid_alpha = _resolve_rerank_config(rerank)
    rerank_external = _resolve_rerank_external_config(rerank)
    rerank_provider: str | None = None
    rerank_model: str | None = None
    rerank_method_effective: str | None = None
    if rerank_enabled:
        rerank_method_effective = str(rerank_method or "").strip() or None
        if rerank_method_effective == "external_rerank_api":
            rerank_provider = "external_rerank_api"
            rerank_model_raw = (rerank_external or {}).get("model")
            rerank_model = str(rerank_model_raw or "").strip() or None
        else:
            rerank_provider = "local"
            rerank_model = None
    rerank_obs = {
        "enabled": bool(rerank_enabled),
        "applied": False,
        "requested_method": rerank_method,
        "method": rerank_method_effective,
        "provider": rerank_provider,
        "model": rerank_model,
        "top_k": int(rerank_top_k),
        "hybrid_alpha": float(rerank_hybrid_alpha),
        "hybrid_applied": False,
        "after_rerank": [],
        "reason": "disabled" if not rerank_enabled else "status_only",
        "error_type": None,
        "before": [],
        "after": [],
        "timing_ms": 0,
        "errors": [],
    }
    if not enabled:
        return {
            "enabled": False,
            "disabled_reason": disabled_reason,
            "query_text": "",
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {"rerank": 0},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
            "backend_preferred": "pgvector" if _prefer_pgvector() else "chroma",
            "hybrid_enabled": bool(getattr(settings, "vector_hybrid_enabled", True)),
            "rerank": rerank_obs,
        }
    return {
        "enabled": True,
        "disabled_reason": None,
        "query_text": "",
        "filters": {"project_id": project_id, "sources": sources},
        "timings_ms": {"rerank": 0},
        "candidates": [],
        "final": {"chunks": [], "text_md": "", "truncated": False},
        "dropped": [],
        "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
        "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
        "backend_preferred": "pgvector" if _prefer_pgvector() else "chroma",
        "hybrid_enabled": bool(getattr(settings, "vector_hybrid_enabled", True)),
        "rerank": rerank_obs,
    }


def schedule_vector_rebuild_task(
    *,
    db: Session | None = None,
    project_id: str,
    actor_user_id: str | None,
    request_id: str | None,
    reason: str,
) -> str | None:
    """
    Fail-soft scheduler: ensure/enqueue a ProjectTask(kind=vector_rebuild) for the project.

    Idempotency key is derived from `ProjectSettings.last_vector_build_at` to avoid task storms while still allowing
    a new task after each successful rebuild.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return None
    reason_norm = str(reason or "").strip() or "dirty"
    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        settings_row = db.get(ProjectSettings, pid)
        if settings_row is not None and not bool(getattr(settings_row, "vector_index_dirty", False)):
            return None

        last_build_at = getattr(settings_row, "last_vector_build_at", None) if settings_row is not None else None
        token = "none"
        if last_build_at is not None:
            token = last_build_at.isoformat().replace("+00:00", "Z")

        idempotency_key = f"vector:project:since:{token}:v1"
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
                kind="vector_rebuild",
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
                kind="vector_rebuild",
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
            event="VECTOR_REBUILD_SCHEDULE_ERROR",
            project_id=pid,
            error_type=type(exc).__name__,
            request_id=request_id,
            **exception_log_fields(exc),
        )
        return None
    finally:
        if owns_session:
            db.close()


def _import_chromadb() -> Any:
    try:
        import chromadb  # type: ignore[import-not-found]

        return chromadb
    except Exception:  # pragma: no cover - env dependent
        return _INMEMORY_CHROMADB


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    n = min(len(a), len(b))
    if n <= 0:
        return 1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        av = float(a[i])
        bv = float(b[i])
        dot += av * bv
        na += av * av
        nb += bv * bv
    if na <= 0.0 or nb <= 0.0:
        return 1.0
    sim = dot / (math.sqrt(na) * math.sqrt(nb))
    if sim > 1.0:
        sim = 1.0
    if sim < -1.0:
        sim = -1.0
    return 1.0 - sim


class _InMemoryCollection:
    def __init__(self, *, name: str, metadata: dict[str, Any] | None = None):
        self._name = str(name)
        self._metadata = dict(metadata or {})
        self._docs: dict[str, str] = {}
        self._metas: dict[str, dict[str, Any]] = {}
        self._embs: dict[str, list[float]] = {}

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        documents = documents or []
        metadatas = metadatas or []
        embeddings = embeddings or []
        for idx, raw_id in enumerate(ids or []):
            doc = documents[idx] if idx < len(documents) else ""
            meta = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
            emb = embeddings[idx] if idx < len(embeddings) else []
            rid = str(raw_id)
            self._docs[rid] = str(doc or "")
            self._metas[rid] = dict(meta)
            self._embs[rid] = [float(x) for x in (emb or [])]

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        q = query_embeddings[0] if query_embeddings else []
        where = where or {}

        def _meta_match(meta: dict[str, Any]) -> bool:
            for k, v in where.items():
                if str(meta.get(k)) != str(v):
                    return False
            return True

        scored: list[tuple[float, str]] = []
        for rid, emb in self._embs.items():
            meta = self._metas.get(rid) or {}
            if where and not _meta_match(meta):
                continue
            dist = _cosine_distance(q, emb)
            scored.append((dist, rid))

        scored.sort(key=lambda x: x[0])
        top = scored[: max(0, int(n_results))]

        ids = [rid for _, rid in top]
        docs = [self._docs.get(rid, "") for rid in ids]
        metas = [self._metas.get(rid, {}) for rid in ids]
        dists = [float(dist) for dist, _ in top]

        return {
            "ids": [ids],
            "documents": [docs],
            "metadatas": [metas],
            "distances": [dists],
        }

    def get(
        self,
        *,
        include: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        ids = list(self._docs.keys())
        off = max(0, int(offset or 0))
        lim = int(limit) if limit is not None else None
        sliced = ids[off : off + lim] if lim is not None else ids[off:]

        out: dict[str, Any] = {"ids": sliced}
        inc = set(include or [])
        if not include or "documents" in inc:
            out["documents"] = [self._docs.get(rid, "") for rid in sliced]
        if not include or "metadatas" in inc:
            out["metadatas"] = [self._metas.get(rid, {}) for rid in sliced]
        if not include or "embeddings" in inc:
            out["embeddings"] = [self._embs.get(rid, []) for rid in sliced]
        return out


_INMEMORY_CHROMA: dict[str, dict[str, _InMemoryCollection]] = {}


class _InMemoryClient:
    def __init__(self, *, path: str):
        self._path = str(path or "inmemory")
        _INMEMORY_CHROMA.setdefault(self._path, {})

    def get_or_create_collection(self, *, name: str, metadata: dict[str, Any] | None = None) -> _InMemoryCollection:
        store = _INMEMORY_CHROMA.setdefault(self._path, {})
        key = str(name)
        col = store.get(key)
        if col is None:
            col = _InMemoryCollection(name=key, metadata=metadata)
            store[key] = col
        return col

    def get_collection(self, *, name: str) -> _InMemoryCollection:
        store = _INMEMORY_CHROMA.get(self._path) or {}
        key = str(name)
        col = store.get(key)
        if col is None:
            raise ValueError("collection does not exist")
        return col

    def delete_collection(self, *, name: str) -> None:
        store = _INMEMORY_CHROMA.get(self._path) or {}
        key = str(name)
        if key not in store:
            raise ValueError("collection does not exist")
        del store[key]


class _InMemoryChromaModule:
    PersistentClient = _InMemoryClient


_INMEMORY_CHROMADB = _InMemoryChromaModule()


def _normalize_kb_id(kb_id: str | None) -> str:
    raw = str(kb_id or "").strip()
    return raw or "default"


def _legacy_collection_name(project_id: str) -> str:
    raw = f"ainovel_{project_id}"
    safe = re.sub(r"[^A-Za-z0-9_\\-]+", "_", raw).strip("_")
    if not safe:
        safe = "ainovel_default"
    return safe[:60]


def _hash_collection_name(project_id: str, kb_id: str | None = None) -> str:
    kb = _normalize_kb_id(kb_id)
    digest = hashlib.sha256(f"{project_id}:{kb}".encode("utf-8")).hexdigest()[:24]
    return f"ainovel_{digest}"


def _chroma_collection_naming() -> str:
    raw = str(getattr(settings, "vector_chroma_collection_naming", "legacy") or "legacy").strip().lower()
    return raw if raw in ("legacy", "hash") else "legacy"


def _migrate_chroma_collection(*, source: Any, target: Any) -> int:
    migrated = 0
    offset = 0
    limit = 1000
    while True:
        batch = source.get(
            include=["documents", "metadatas", "embeddings"],
            limit=limit,
            offset=offset,
        )
        ids = batch.get("ids") or []
        if not ids:
            break
        target.upsert(
            ids=ids,
            documents=batch.get("documents"),
            metadatas=batch.get("metadatas"),
            embeddings=batch.get("embeddings"),
        )
        migrated += len(ids)
        offset += len(ids)
    return migrated


def _get_collection(*, project_id: str, kb_id: str | None = None):
    chromadb = _import_chromadb()
    persist_dir = settings.vector_chroma_persist_dir or _default_chroma_persist_dir()
    client = chromadb.PersistentClient(path=persist_dir)

    kb = _normalize_kb_id(kb_id)
    legacy_name = _legacy_collection_name(project_id)
    hash_name = _hash_collection_name(project_id, kb)

    naming = _chroma_collection_naming()
    if naming == "legacy" and kb == "default":
        return client.get_or_create_collection(
            name=legacy_name,
            metadata={"project_id": project_id, "kb_id": kb, "naming": "legacy"},
        )

    if kb != "default":
        return client.get_or_create_collection(
            name=hash_name,
            metadata={"project_id": project_id, "kb_id": kb, "naming": "hash"},
        )

    try:
        return client.get_collection(name=hash_name)
    except Exception:
        pass

    try:
        legacy_collection = client.get_collection(name=legacy_name)
    except Exception:
        legacy_collection = None

    if legacy_collection is None:
        return client.get_or_create_collection(
            name=hash_name,
            metadata={"project_id": project_id, "kb_id": kb, "naming": "hash"},
        )

    t0 = time.perf_counter()
    migrated = 0
    try:
        hash_collection = client.get_or_create_collection(
            name=hash_name,
            metadata={"project_id": project_id, "kb_id": kb, "naming": "hash", "migrated_from": legacy_name},
        )
        migrated = _migrate_chroma_collection(source=legacy_collection, target=hash_collection)
        try:
            client.delete_collection(name=legacy_name)
        except Exception as exc:  # pragma: no cover - env dependent
            log_event(
                logger,
                "warning",
                event="VECTOR_RAG",
                action="collection_migrate_cleanup",
                project_id=project_id,
                backend="chroma",
                from_collection=legacy_name,
                to_collection=hash_name,
                migrated=migrated,
                error_type=type(exc).__name__,
                **exception_log_fields(exc),
            )
        log_event(
            logger,
            "info",
            event="VECTOR_RAG",
            action="collection_migrate",
            project_id=project_id,
            backend="chroma",
            from_collection=legacy_name,
            to_collection=hash_name,
            migrated=migrated,
            timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
        )
        return hash_collection
    except Exception as exc:  # pragma: no cover - env dependent
        try:
            client.delete_collection(name=hash_name)
        except Exception:
            pass
        log_event(
            logger,
            "warning",
            event="VECTOR_RAG",
            action="collection_migrate",
            project_id=project_id,
            backend="chroma",
            from_collection=legacy_name,
            to_collection=hash_name,
            migrated=migrated,
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
            timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
        )
        return legacy_collection


def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    if chunk_size <= 0:
        return [s]

    out: list[str] = []
    start = 0
    overlap = max(0, min(int(overlap), int(chunk_size) - 1)) if chunk_size > 1 else 0
    while start < len(s):
        end = min(len(s), start + chunk_size)
        piece = s[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(s):
            break
        start = max(0, end - overlap)
    return out


def build_project_chunks(*, db: Session, project_id: str, sources: list[VectorSource] | None = None) -> list[VectorChunk]:
    sources = sources or list(_ALL_SOURCES)
    chunk_size = int(settings.vector_chunk_size or 800)
    overlap = int(settings.vector_chunk_overlap or 120)

    out: list[VectorChunk] = []

    if "worldbook" in sources:
        rows = (
            db.execute(
                select(WorldBookEntry)
                .where(WorldBookEntry.project_id == project_id)
                .where(WorldBookEntry.enabled == True)  # noqa: E712
                .order_by(WorldBookEntry.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for e in rows:
            title = (e.title or "").strip()
            content = (e.content_md or "").strip()
            text = f"{title}\n\n{content}".strip()
            for idx, chunk in enumerate(_chunk_text(text, chunk_size=chunk_size, overlap=overlap)):
                out.append(
                    VectorChunk(
                        id=f"worldbook:{e.id}:{idx}",
                        text=chunk,
                        metadata={
                            "project_id": project_id,
                            "source": "worldbook",
                            "source_id": e.id,
                            "title": title,
                            "chunk_index": idx,
                        },
                    )
                )

    if "outline" in sources:
        rows = (
            db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.updated_at.desc()))
            .scalars()
            .all()
        )
        for o in rows:
            title = (o.title or "").strip()
            content = (o.content_md or "").strip()
            text = f"{title}\n\n{content}".strip()
            for idx, chunk in enumerate(_chunk_text(text, chunk_size=chunk_size, overlap=overlap)):
                out.append(
                    VectorChunk(
                        id=f"outline:{o.id}:{idx}",
                        text=chunk,
                        metadata={
                            "project_id": project_id,
                            "source": "outline",
                            "source_id": o.id,
                            "title": title,
                            "chunk_index": idx,
                        },
                    )
                )

    if "chapter" in sources:
        rows = (
            db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.updated_at.desc()))
            .scalars()
            .all()
        )
        for c in rows:
            title = (c.title or "").strip()
            content = (c.content_md or "").strip()
            if not content:
                continue
            header = f"第 {int(c.number)} 章：{title}".strip("：")
            text = f"{header}\n\n{content}".strip()
            for idx, chunk in enumerate(_chunk_text(text, chunk_size=chunk_size, overlap=overlap)):
                out.append(
                    VectorChunk(
                        id=f"chapter:{c.id}:{idx}",
                        text=chunk,
                        metadata={
                            "project_id": project_id,
                            "source": "chapter",
                            "source_id": c.id,
                            "chapter_number": int(c.number),
                            "title": title,
                            "chunk_index": idx,
                        },
                    )
                )

    if "story_memory" in sources:
        rows = (
            db.execute(select(StoryMemory).where(StoryMemory.project_id == project_id).order_by(StoryMemory.updated_at.desc()))
            .scalars()
            .all()
        )
        for m in rows:
            title = (m.title or "").strip()
            content = (m.content or "").strip()
            if not content:
                continue
            header = f"[{str(m.memory_type or '').strip() or 'story_memory'}] {title}".strip()
            text = f"{header}\n\n{content}".strip() if header else content
            for idx, chunk in enumerate(_chunk_text(text, chunk_size=chunk_size, overlap=overlap)):
                out.append(
                    VectorChunk(
                        id=f"story_memory:{m.id}:{idx}",
                        text=chunk,
                        metadata={
                            "project_id": project_id,
                            "source": "story_memory",
                            "source_id": m.id,
                            "title": title,
                            "chunk_index": idx,
                            "memory_type": str(m.memory_type or "").strip(),
                            "chapter_id": str(m.chapter_id or "") or None,
                            "story_timeline": int(m.story_timeline or 0),
                            "is_foreshadow": bool(int(m.is_foreshadow or 0)),
                        },
                    )
                )

    return out


def _pgvector_upsert_chunks(*, project_id: str, chunks: list[VectorChunk], embeddings: list[list[float]]) -> dict[str, Any]:
    sql = text(
        """
        INSERT INTO vector_chunks (
            id,
            project_id,
            source,
            source_id,
            chunk_index,
            title,
            chapter_number,
            text_md,
            metadata_json,
            embedding,
            updated_at
        ) VALUES (
            :id,
            :project_id,
            :source,
            :source_id,
            :chunk_index,
            :title,
            :chapter_number,
            :text_md,
            :metadata_json,
            (:embedding)::vector,
            NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            project_id = EXCLUDED.project_id,
            source = EXCLUDED.source,
            source_id = EXCLUDED.source_id,
            chunk_index = EXCLUDED.chunk_index,
            title = EXCLUDED.title,
            chapter_number = EXCLUDED.chapter_number,
            text_md = EXCLUDED.text_md,
            metadata_json = EXCLUDED.metadata_json,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        """.strip()
    )

    params: list[dict[str, Any]] = []
    for c, emb in zip(chunks, embeddings):
        meta = c.metadata if isinstance(c.metadata, dict) else {}
        source = str(meta.get("source") or "")
        source_id = str(meta.get("source_id") or "")
        try:
            chunk_index = int(meta.get("chunk_index") or 0)
        except Exception:
            chunk_index = 0
        title = str(meta.get("title") or "").strip() or None
        chapter_number = meta.get("chapter_number")
        try:
            chapter_number_int = int(chapter_number) if chapter_number is not None else None
        except Exception:
            chapter_number_int = None

        params.append(
            {
                "id": c.id,
                "project_id": project_id,
                "source": source,
                "source_id": source_id,
                "chunk_index": chunk_index,
                "title": title,
                "chapter_number": chapter_number_int,
                "text_md": c.text,
                "metadata_json": json.dumps(meta, ensure_ascii=False),
                "embedding": _pgvector_literal([float(x) for x in emb]),
            }
        )

    if not params:
        return {"enabled": True, "skipped": False, "ingested": 0}

    db = SessionLocal()
    try:
        db.execute(sql, params)
        db.commit()
    finally:
        db.close()
    return {"enabled": True, "skipped": False, "ingested": len(params)}


def _pgvector_delete_project(*, project_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM vector_chunks WHERE project_id = :project_id"), {"project_id": project_id})
        db.commit()
    finally:
        db.close()


def _pgvector_hybrid_fetch(
    *,
    project_id: str,
    query_text: str,
    query_vec: list[float],
    sources: list[VectorSource],
    vector_k: int,
    fts_k: int,
    rrf_k: int,
) -> dict[str, Any]:
    qvec = _pgvector_literal(query_vec)
    qtext = (query_text or "").strip() or " "

    where_sql = "project_id = :project_id"
    base_params: dict[str, Any] = {"project_id": project_id, "qvec": qvec, "qtext": qtext}
    if len(sources) == 1:
        where_sql += " AND source = :source"
        base_params["source"] = sources[0]
    elif sources:
        where_sql += " AND source = ANY((:sources)::text[])"
        base_params["sources"] = sources

    vec_sql = text(
        f"""
        SELECT id, (embedding <=> (:qvec)::vector) AS distance
        FROM {_PGVECTOR_TABLE}
        WHERE {where_sql}
        ORDER BY embedding <=> (:qvec)::vector ASC
        LIMIT :limit
        """.strip()
    )
    fts_sql = text(
        f"""
        SELECT id, ts_rank_cd(content_tsv, plainto_tsquery('simple', :qtext)) AS score
        FROM {_PGVECTOR_TABLE}
        WHERE {where_sql} AND content_tsv @@ plainto_tsquery('simple', :qtext)
        ORDER BY score DESC
        LIMIT :limit
        """.strip()
    )

    db = SessionLocal()
    try:
        vec_rows = db.execute(vec_sql, {**base_params, "limit": int(vector_k)}).all()
        fts_rows = db.execute(fts_sql, {**base_params, "limit": int(fts_k)}).all()

        vec_ids = [str(r[0]) for r in vec_rows]
        fts_ids = [str(r[0]) for r in fts_rows]
        ids = list(dict.fromkeys([*vec_ids, *fts_ids]).keys())
        if not ids:
            return {
                "candidates": [],
                "ranks": {"vector": {}, "fts": {}, "rrf_k": int(rrf_k)},
                "counts": {"vector": 0, "fts": 0, "union": 0},
            }

        vec_ranks = {cid: i + 1 for i, cid in enumerate(vec_ids)}
        fts_ranks = {cid: i + 1 for i, cid in enumerate(fts_ids)}

        details_sql = text(
            f"""
            SELECT
                id,
                text_md,
                metadata_json,
                (embedding <=> (:qvec)::vector) AS distance,
                ts_rank_cd(content_tsv, plainto_tsquery('simple', :qtext)) AS fts_score
            FROM {_PGVECTOR_TABLE}
            WHERE id = ANY((:ids)::text[])
            """.strip()
        )
        rows = db.execute(details_sql, {**base_params, "ids": ids}).all()
    finally:
        db.close()

    candidates: list[dict[str, Any]] = []
    for r in rows:
        cid = str(r[0])
        text_md = str(r[1] or "")
        meta = _safe_json_loads(str(r[2] or ""))
        try:
            distance = float(r[3])
        except Exception:
            distance = 0.0
        try:
            fts_score = float(r[4]) if r[4] is not None else 0.0
        except Exception:
            fts_score = 0.0

        vrank = vec_ranks.get(cid)
        frank = fts_ranks.get(cid)
        rrf_score = _rrf_score(vector_rank=vrank, fts_rank=frank, k=int(rrf_k))

        hybrid_meta = {
            "vector_rank": vrank,
            "fts_rank": frank,
            "rrf_k": int(rrf_k),
            "rrf_score": rrf_score,
            "fts_score": fts_score,
        }
        if isinstance(meta.get("hybrid"), dict):
            meta["hybrid"] = {**(meta.get("hybrid") or {}), **hybrid_meta}
        else:
            meta["hybrid"] = hybrid_meta

        candidates.append(
            {
                "id": cid,
                "distance": distance,
                "text": text_md,
                "metadata": meta,
                "hybrid": hybrid_meta,
                "_rrf_score": rrf_score,
            }
        )

    candidates.sort(key=lambda c: (-float(c.get("_rrf_score") or 0.0), float(c.get("distance") or 0.0)))

    return {
        "candidates": candidates,
        "ranks": {"vector": vec_ranks, "fts": fts_ranks, "rrf_k": int(rrf_k)},
        "counts": {"vector": len(vec_rows), "fts": len(fts_rows), "union": len(ids)},
    }


def _pgvector_hybrid_query(*, project_id: str, query_text: str, query_vec: list[float], sources: list[VectorSource]) -> dict[str, Any]:
    if not _is_postgres():
        raise RuntimeError("not_postgres")

    top_k = int(settings.vector_max_candidates or 20)
    rrf_k = int(settings.vector_hybrid_rrf_k or 60)
    vec_k = top_k
    fts_k = top_k

    overfilter_actions: list[str] = []
    requested_sources = list(sources or _ALL_SOURCES)
    used_sources = list(requested_sources)

    min_needed = max(1, min(3, int(settings.vector_final_max_chunks or 6)))
    for _attempt in range(3):
        out = _pgvector_hybrid_fetch(
            project_id=project_id,
            query_text=query_text,
            query_vec=query_vec,
            sources=used_sources,
            vector_k=vec_k,
            fts_k=fts_k,
            rrf_k=rrf_k,
        )
        union_count = int(out.get("counts", {}).get("union") or 0)
        if not settings.vector_overfiltering_enabled:
            break
        if union_count >= min_needed:
            break
        if used_sources != _ALL_SOURCES:
            used_sources = list(_ALL_SOURCES)
            overfilter_actions.append("relax_sources")
            continue
        if vec_k <= top_k:
            vec_k = min(200, max(top_k * 3, top_k))
            fts_k = min(200, max(top_k * 3, top_k))
            overfilter_actions.append("expand_candidates")
            continue
        break

    return {
        **out,
        "overfilter": {
            "enabled": bool(settings.vector_overfiltering_enabled),
            "min_needed": min_needed,
            "requested_sources": requested_sources,
            "used_sources": used_sources,
            "actions": overfilter_actions,
            "vector_k": vec_k,
            "fts_k": fts_k,
        },
    }


def ingest_chunks(
    *,
    project_id: str,
    kb_id: str | None = None,
    chunks: list[VectorChunk],
    embedding: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    enabled, disabled_reason = _vector_enabled_reason(embedding=embedding)
    if not enabled:
        return {"enabled": False, "skipped": True, "disabled_reason": disabled_reason, "ingested": 0}

    start = time.perf_counter()
    texts = [c.text for c in chunks]
    ids = [c.id for c in chunks]
    metadatas = [c.metadata for c in chunks]

    embeddings: list[list[float]] = []
    if texts:
        embed_out = embed_texts_with_providers(texts, embedding=embedding)
        if not bool(embed_out.get("enabled")):
            disabled = str(embed_out.get("disabled_reason") or "error")
            log_event(
                logger,
                "warning",
                event="VECTOR_RAG",
                action="ingest",
                project_id=project_id,
                disabled_reason=disabled,
                error_type="EmbeddingError",
            )
            return {
                "enabled": False,
                "skipped": True,
                "disabled_reason": disabled,
                "error": embed_out.get("error"),
                "ingested": 0,
            }
        embeddings = embed_out.get("vectors") or []

    embed_ms = int((time.perf_counter() - start) * 1000)

    if _prefer_pgvector():
        try:
            write_start = time.perf_counter()
            out = _pgvector_upsert_chunks(project_id=project_id, chunks=chunks, embeddings=embeddings)
            write_ms = int((time.perf_counter() - write_start) * 1000)
            log_event(
                logger,
                "info",
                event="VECTOR_RAG",
                action="ingest",
                project_id=project_id,
                chunks=len(chunks),
                timings_ms={"embed": embed_ms, "upsert": write_ms},
                backend="pgvector",
            )
            return {**out, "timings_ms": {"embed": embed_ms, "upsert": write_ms}, "backend": "pgvector"}
        except Exception as exc:  # pragma: no cover - env dependent
            log_event(
                logger,
                "warning",
                event="VECTOR_RAG",
                action="ingest",
                project_id=project_id,
                backend="pgvector",
                fallback="chroma",
                error_type=type(exc).__name__,
            )

    try:
        collection = _get_collection(project_id=project_id, kb_id=kb_id)
    except Exception as exc:  # pragma: no cover - env dependent
        return {"enabled": False, "skipped": True, "disabled_reason": "chroma_unavailable", "error": str(exc), "ingested": 0}

    write_start = time.perf_counter()
    collection.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)
    write_ms = int((time.perf_counter() - write_start) * 1000)

    log_event(
        logger,
        "info",
        event="VECTOR_RAG",
        action="ingest",
        project_id=project_id,
        chunks=len(chunks),
        timings_ms={"embed": embed_ms, "upsert": write_ms},
        backend="chroma",
    )
    return {"enabled": True, "skipped": False, "ingested": len(chunks), "timings_ms": {"embed": embed_ms, "upsert": write_ms}, "backend": "chroma"}


def rebuild_project(
    *,
    project_id: str,
    kb_id: str | None = None,
    chunks: list[VectorChunk],
    embedding: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    enabled, disabled_reason = _vector_enabled_reason(embedding=embedding)
    if not enabled:
        return {"enabled": False, "skipped": True, "disabled_reason": disabled_reason, "rebuilt": 0}

    if _prefer_pgvector():
        try:
            _pgvector_delete_project(project_id=project_id)
        except Exception as exc:  # pragma: no cover - env dependent
            log_event(
                logger,
                "warning",
                event="VECTOR_RAG",
                action="rebuild",
                project_id=project_id,
                backend="pgvector",
                error_type=type(exc).__name__,
            )
        out = ingest_chunks(project_id=project_id, kb_id=kb_id, chunks=chunks, embedding=embedding)
        return {"enabled": bool(out.get("enabled")), "skipped": bool(out.get("skipped")), "rebuilt": int(out.get("ingested") or 0), **out}

    try:
        chromadb = _import_chromadb()
        persist_dir = settings.vector_chroma_persist_dir or _default_chroma_persist_dir()
        client = chromadb.PersistentClient(path=persist_dir)
        kb = _normalize_kb_id(kb_id)
        legacy_name = _legacy_collection_name(project_id)
        hash_name = _hash_collection_name(project_id, kb)
        naming = _chroma_collection_naming()
        if kb != "default":
            names = {hash_name}
        else:
            names = {legacy_name} if naming == "legacy" else {hash_name, legacy_name}
        for name in names:
            try:
                client.delete_collection(name=name)
            except Exception:
                pass
    except Exception as exc:  # pragma: no cover - env dependent
        return {"enabled": False, "skipped": True, "disabled_reason": "chroma_unavailable", "error": str(exc), "rebuilt": 0}

    out = ingest_chunks(project_id=project_id, kb_id=kb_id, chunks=chunks, embedding=embedding)
    return {"enabled": bool(out.get("enabled")), "skipped": bool(out.get("skipped")), "rebuilt": int(out.get("ingested") or 0), **out}


def purge_project_vectors(*, project_id: str, kb_id: str | None = None) -> dict[str, Any]:
    """
    Best-effort deletion of vector index data for the given project.

    - Postgres: delete rows in vector_chunks (pgvector backend).
    - SQLite: delete Chroma collection (if chromadb is installed).
    """
    t0 = time.perf_counter()

    if _prefer_pgvector():
        try:
            _pgvector_delete_project(project_id=project_id)
            out = {"enabled": True, "skipped": False, "deleted": True, "backend": "pgvector"}
            log_event(
                logger,
                "info",
                event="VECTOR_RAG",
                action="purge",
                project_id=project_id,
                backend="pgvector",
                deleted=True,
                timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
            )
            out["timings_ms"] = {"total": int((time.perf_counter() - t0) * 1000)}
            return out
        except Exception as exc:  # pragma: no cover - env dependent
            log_event(
                logger,
                "warning",
                event="VECTOR_RAG",
                action="purge",
                project_id=project_id,
                backend="pgvector",
                deleted=False,
                error_type=type(exc).__name__,
                timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
            )
            return {
                "enabled": True,
                "skipped": True,
                "deleted": False,
                "backend": "pgvector",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "timings_ms": {"total": int((time.perf_counter() - t0) * 1000)},
            }

    try:
        chromadb = _import_chromadb()
        persist_dir = settings.vector_chroma_persist_dir or _default_chroma_persist_dir()
        client = chromadb.PersistentClient(path=persist_dir)
        kb = _normalize_kb_id(kb_id)
        names = [_hash_collection_name(project_id, kb)]
        if kb == "default":
            names.append(_legacy_collection_name(project_id))
        delete_errors: list[str] = []
        delete_error_type: str | None = None
        deleted = True
        for name in names:
            try:
                client.delete_collection(name=name)
            except Exception as exc:  # pragma: no cover - env dependent
                msg = str(exc)
                msg_lower = msg.lower()
                if "does not exist" in msg_lower or "not found" in msg_lower:
                    continue
                deleted = False
                delete_errors.append(f"{name}: {msg}")
                delete_error_type = delete_error_type or type(exc).__name__

        error = "; ".join(delete_errors) if delete_errors else None
        error_type = delete_error_type

        out: dict[str, Any] = {
            "enabled": True,
            "skipped": False,
            "deleted": bool(deleted),
            "backend": "chroma",
            "timings_ms": {"total": int((time.perf_counter() - t0) * 1000)},
        }
        if error:
            out.update({"error": error, "error_type": error_type})
            log_event(
                logger,
                "warning",
                event="VECTOR_RAG",
                action="purge",
                project_id=project_id,
                backend="chroma",
                deleted=bool(deleted),
                error_type=error_type,
                timings_ms=out["timings_ms"],
            )
        else:
            log_event(
                logger,
                "info",
                event="VECTOR_RAG",
                action="purge",
                project_id=project_id,
                backend="chroma",
                deleted=True,
                timings_ms=out["timings_ms"],
            )
        return out
    except Exception as exc:  # pragma: no cover - env dependent
        log_event(
            logger,
            "warning",
            event="VECTOR_RAG",
            action="purge",
            project_id=project_id,
            backend="chroma",
            deleted=False,
            error_type=type(exc).__name__,
            timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
        )
        return {
            "enabled": False,
            "skipped": True,
            "deleted": False,
            "backend": "chroma",
            "disabled_reason": "chroma_unavailable",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "timings_ms": {"total": int((time.perf_counter() - t0) * 1000)},
        }


def _format_final_text(chunks: list[dict[str, Any]], *, char_limit: int) -> tuple[str, bool]:
    parts: list[str] = []
    for c in chunks:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        source = str(meta.get("source") or "")
        title = str(meta.get("title") or "").strip()
        if source == "worldbook":
            header = f"【世界书：{title or meta.get('source_id') or 'entry'}】"
        elif source == "chapter":
            n = meta.get("chapter_number")
            header = f"【章节 {n}：{title or meta.get('source_id') or 'chapter'}】"
        elif source == "outline":
            header = f"【大纲：{title or meta.get('source_id') or 'outline'}】"
        elif source == "story_memory":
            mtype = str(meta.get("memory_type") or "").strip() or "story_memory"
            header = f"【记忆：{mtype}：{title or meta.get('source_id') or 'memory'}】".rstrip("：")
        else:
            header = f"【{source or 'chunk'}】"
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"{header}\n{text}".strip())

    inner = "\n\n---\n\n".join(parts).strip()
    truncated = False
    if char_limit >= 0 and inner and len(inner) > char_limit:
        inner = inner[:char_limit].rstrip()
        truncated = True
    if not inner:
        return "", False
    return f"<VECTOR_RAG>\n{inner}\n</VECTOR_RAG>", truncated


def query_project(
    *,
    project_id: str,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,
    query_text: str,
    sources: list[VectorSource] | None = None,
    embedding: dict[str, str | None] | None = None,
    rerank: dict[str, Any] | None = None,
    super_sort: dict[str, Any] | None = None,
    kb_weights: dict[str, float] | None = None,
    kb_orders: dict[str, int] | None = None,
    kb_priority_groups: dict[str, str] | None = None,
) -> dict[str, Any]:
    raw_kb_ids = kb_ids if kb_ids is not None else ([kb_id] if kb_id is not None else [])
    selected_kb_ids: list[str] = []
    seen_kb: set[str] = set()
    for raw in raw_kb_ids:
        normalized = _normalize_kb_id(str(raw or "").strip() or None)
        if normalized in seen_kb:
            continue
        seen_kb.add(normalized)
        selected_kb_ids.append(normalized)
    if not selected_kb_ids:
        selected_kb_ids = [_normalize_kb_id(None)]

    weights_by_kb_full = {kb: float((kb_weights or {}).get(kb, 1.0)) for kb in selected_kb_ids}
    orders_by_kb_full = {kb: int((kb_orders or {}).get(kb, 999)) for kb in selected_kb_ids}
    priority_groups_by_kb_full = {kb: _normalize_kb_priority_group((kb_priority_groups or {}).get(kb)) for kb in selected_kb_ids}

    if _prefer_pgvector() and len(selected_kb_ids) > 1:
        selected_kb_ids = [
            sorted(
                selected_kb_ids,
                key=lambda kb: (
                    0 if priority_groups_by_kb_full.get(kb) == "high" else 1,
                    int(orders_by_kb_full.get(kb, 999)),
                    str(kb),
                ),
            )[0]
        ]

    weights_by_kb = {kb: float(weights_by_kb_full.get(kb, 1.0)) for kb in selected_kb_ids}
    orders_by_kb = {kb: int(orders_by_kb_full.get(kb, 999)) for kb in selected_kb_ids}
    priority_groups_by_kb = {kb: str(priority_groups_by_kb_full.get(kb, "normal") or "normal") for kb in selected_kb_ids}

    sources = sources or list(_ALL_SOURCES)
    enabled, disabled_reason = _vector_enabled_reason(embedding=embedding)
    rerank_enabled, rerank_method, rerank_top_k, rerank_hybrid_alpha = _resolve_rerank_config(rerank)
    rerank_external = _resolve_rerank_external_config(rerank)
    rerank_provider: str | None = None
    rerank_model: str | None = None
    rerank_method_effective: str | None = None
    if rerank_enabled:
        rerank_method_effective = str(rerank_method or "").strip() or None
        if rerank_method_effective == "external_rerank_api":
            rerank_provider = "external_rerank_api"
            rerank_model_raw = (rerank_external or {}).get("model")
            rerank_model = str(rerank_model_raw or "").strip() or None
        else:
            rerank_provider = "local"
            rerank_model = None
    if not enabled:
        rerank_obs = {
            "enabled": bool(rerank_enabled),
            "applied": False,
            "requested_method": rerank_method,
            "method": rerank_method_effective,
            "provider": rerank_provider,
            "model": rerank_model,
            "top_k": int(rerank_top_k),
            "hybrid_alpha": float(rerank_hybrid_alpha),
            "hybrid_applied": False,
            "after_rerank": [],
            "reason": "vector_disabled",
            "error_type": None,
            "before": [],
            "after": [],
            "timing_ms": 0,
            "errors": [],
        }
        return {
            "enabled": False,
            "disabled_reason": disabled_reason,
            "query_text": query_text,
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {"rerank": 0},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
            "rerank": rerank_obs,
            "kbs": {
                "selected": selected_kb_ids,
                "weights": weights_by_kb,
                "orders": orders_by_kb,
                "priority_groups": priority_groups_by_kb,
                "merge": {"mode": "none", "reason": "vector_disabled"},
                "per_kb": {},
            },
        }

    start = time.perf_counter()
    embed_out = embed_texts_with_providers([query_text.strip() or " "], embedding=embedding)
    embed_ms = int((time.perf_counter() - start) * 1000)
    if not bool(embed_out.get("enabled")):
        disabled = str(embed_out.get("disabled_reason") or "error")
        error = embed_out.get("error")
        rerank_obs = {
            "enabled": bool(rerank_enabled),
            "applied": False,
            "requested_method": rerank_method,
            "method": None,
            "provider": None,
            "model": None,
            "top_k": int(rerank_top_k),
            "hybrid_alpha": float(rerank_hybrid_alpha),
            "hybrid_applied": False,
            "after_rerank": [],
            "reason": "vector_error" if disabled == "error" else "vector_disabled",
            "error_type": "EmbeddingError" if error else None,
            "before": [],
            "after": [],
            "timing_ms": 0,
            "errors": [],
        }
        return {
            "enabled": False,
            "disabled_reason": disabled,
            "error": error,
            "error_type": "EmbeddingError" if error else None,
            "query_text": query_text,
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {"embed": embed_ms, "rerank": 0},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
            "rerank": rerank_obs,
            "kbs": {
                "selected": selected_kb_ids,
                "weights": weights_by_kb,
                "orders": orders_by_kb,
                "priority_groups": priority_groups_by_kb,
                "merge": {"mode": "none", "reason": str(disabled)},
                "per_kb": {},
            },
        }

    qvec = (embed_out.get("vectors") or [[]])[0]

    top_k = int(settings.vector_max_candidates or 20)
    pgvector_error: str | None = None
    if _prefer_pgvector() and bool(getattr(settings, "vector_hybrid_enabled", True)):
        query_start = time.perf_counter()
        try:
            hybrid_out = _pgvector_hybrid_query(project_id=project_id, query_text=query_text, query_vec=qvec, sources=sources)
            query_ms = int((time.perf_counter() - query_start) * 1000)

            raw_candidates = hybrid_out.get("candidates") if isinstance(hybrid_out.get("candidates"), list) else []
            candidates: list[dict[str, Any]] = []
            for c in raw_candidates:
                if not isinstance(c, dict):
                    continue
                cc = dict(c)
                cc.pop("_rrf_score", None)
                candidates.append(cc)

            trimmed_candidates = candidates[:top_k]
            if not rerank_enabled:
                before_ids = [str(c.get("id") or "") for c in trimmed_candidates if isinstance(c, dict)]
                rerank_obs: dict[str, Any] = {
                    "enabled": False,
                    "applied": False,
                    "requested_method": rerank_method,
                    "method": None,
                    "provider": None,
                    "model": None,
                    "top_k": int(rerank_top_k),
                    "hybrid_alpha": float(rerank_hybrid_alpha),
                    "hybrid_applied": False,
                    "after_rerank": list(before_ids),
                    "reason": "disabled",
                    "error_type": None,
                    "before": before_ids,
                    "after": list(before_ids),
                    "timing_ms": 0,
                    "errors": [],
                }
            elif trimmed_candidates:
                trimmed_candidates, rerank_obs = _rerank_candidates(
                    query_text=query_text,
                    candidates=trimmed_candidates,
                    method=rerank_method,
                    top_k=rerank_top_k,
                    hybrid_alpha=rerank_hybrid_alpha,
                    external=rerank_external,
                )
            else:
                rerank_obs = {
                    "enabled": True,
                    "applied": False,
                    "requested_method": rerank_method,
                    "method": None,
                    "provider": None,
                    "model": None,
                    "top_k": int(rerank_top_k),
                    "hybrid_alpha": float(rerank_hybrid_alpha),
                    "hybrid_applied": False,
                    "after_rerank": [],
                    "reason": "empty_candidates",
                    "error_type": None,
                    "before": [],
                    "after": [],
                    "timing_ms": 0,
                    "errors": [],
                }
            dropped: list[dict[str, Any]] = []
            final_chunks: list[dict[str, Any]] = []
            seen_chunk_keys: set[tuple[str, str, int]] = set()
            selected_by_source: dict[tuple[str, str], int] = {}
            max_chunks = int(settings.vector_final_max_chunks or 6)
            max_chunks = max(1, min(int(max_chunks), 1000))
            per_source_max_chunks = int(getattr(settings, "vector_per_source_id_max_chunks", 1) or 1)
            per_source_max_chunks = max(1, min(int(per_source_max_chunks), 1000))
            processed = 0
            for c in trimmed_candidates:
                processed += 1
                source_key = _vector_candidate_key(c)
                chunk_key = _vector_candidate_chunk_key(c)
                if chunk_key in seen_chunk_keys:
                    dropped.append({"id": c.get("id"), "reason": "duplicate_chunk"})
                    continue
                seen_chunk_keys.add(chunk_key)
                if selected_by_source.get(source_key, 0) >= per_source_max_chunks:
                    dropped.append({"id": c.get("id"), "reason": "per_source_budget"})
                    continue
                final_chunks.append(c)
                selected_by_source[source_key] = selected_by_source.get(source_key, 0) + 1
                if len(final_chunks) >= max_chunks:
                    break

            if len(final_chunks) >= max_chunks:
                for c in trimmed_candidates[processed:]:
                    dropped.append({"id": c.get("id"), "reason": "budget"})

            final_chunks, super_sort_obs = _super_sort_final_chunks(final_chunks, super_sort=super_sort)

            final_char_limit = int(settings.vector_final_char_limit or 6000)
            post_start = time.perf_counter()
            text_md, truncated = _format_final_text(final_chunks, char_limit=final_char_limit)
            post_ms = int((time.perf_counter() - post_start) * 1000)

            timings_ms = {"embed": embed_ms, "query": query_ms, "post": post_ms, "rerank": int(rerank_obs.get("timing_ms") or 0)}
            obs_counts = _build_vector_query_counts(
                candidates_total=len(candidates),
                returned_candidates=trimmed_candidates,
                final_selected=len(final_chunks),
                dropped=dropped,
            )
            budget_obs = _vector_budget_observability(
                top_k=top_k,
                max_chunks=max_chunks,
                per_source_max_chunks=per_source_max_chunks,
                char_limit=final_char_limit,
                dropped=dropped,
            )
            log_event(
                logger,
                "info",
                event="VECTOR_RAG",
                action="query",
                project_id=project_id,
                backend="pgvector",
                hybrid_enabled=True,
                query_chars=len(query_text or ""),
                candidates=[c.get("id") for c in trimmed_candidates[: min(5, len(trimmed_candidates))]],
                dropped=dropped[:5],
                timings_ms=timings_ms,
                filters={"sources": sources},
                overfilter=hybrid_out.get("overfilter"),
                counts=hybrid_out.get("counts"),
                rerank=rerank_obs,
                super_sort=super_sort_obs,
            )

            return {
                "enabled": True,
                "disabled_reason": None,
                "query_text": query_text,
                "filters": {"project_id": project_id, "sources": sources},
                "timings_ms": timings_ms,
                "candidates": trimmed_candidates,
                "final": {"chunks": final_chunks, "text_md": text_md, "truncated": truncated},
                "dropped": dropped,
                "counts": obs_counts,
                "budget_observability": budget_obs,
                "rerank": rerank_obs,
                "super_sort": super_sort_obs,
                "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": text_md},
                "backend": "pgvector",
                "hybrid": {
                    "enabled": True,
                    "ranks": hybrid_out.get("ranks"),
                    "counts": hybrid_out.get("counts"),
                    "overfilter": hybrid_out.get("overfilter"),
                },
            }
        except Exception as exc:  # pragma: no cover - env dependent
            pgvector_error = type(exc).__name__

    per_kb: dict[str, Any] = {}
    per_kb_candidates: dict[str, list[dict[str, Any]]] = {}
    query_ms = 0

    for kid in selected_kb_ids:
        try:
            collection = _get_collection(project_id=project_id, kb_id=kid)
        except Exception as exc:  # pragma: no cover - env dependent
            per_kb[kid] = {
                "enabled": False,
                "disabled_reason": "chroma_unavailable",
                "error": str(exc),
                "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
                "overfilter": None,
                "weight": float(weights_by_kb.get(kid, 1.0)),
                "order": int(orders_by_kb.get(kid, 999)),
                "priority_group": str(priority_groups_by_kb.get(kid, "normal") or "normal"),
            }
            continue

        query_start = time.perf_counter()
        where: dict[str, Any] | None = None
        if len(sources) == 1:
            where = {"source": sources[0]}
        result = collection.query(
            query_embeddings=[qvec],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        query_ms += int((time.perf_counter() - query_start) * 1000)

        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]

        candidates: list[dict[str, Any]] = []
        for idx in range(min(len(ids), len(docs), len(metas), len(dists))):
            meta = metas[idx] if isinstance(metas[idx], dict) else {}
            if sources and str(meta.get("source") or "") not in sources:
                continue
            m = dict(meta)
            m.setdefault("kb_id", kid)
            candidates.append(
                {
                    "id": str(ids[idx]),
                    "distance": float(dists[idx]),
                    "text": str(docs[idx] or ""),
                    "metadata": m,
                }
            )

        per_kb_candidates[kid] = candidates
        per_kb[kid] = {
            "enabled": True,
            "disabled_reason": None,
            "counts": _build_vector_query_counts(candidates_total=len(candidates), returned_candidates=candidates[:top_k], final_selected=0, dropped=[]),
            "overfilter": None,
            "weight": float(weights_by_kb.get(kid, 1.0)),
            "order": int(orders_by_kb.get(kid, 999)),
            "priority_group": str(priority_groups_by_kb.get(kid, "normal") or "normal"),
        }

    if not per_kb_candidates:
        out: dict[str, Any] = {
            "enabled": False,
            "disabled_reason": "chroma_unavailable",
            "error": "no_collections",
            "query_text": query_text,
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {"embed": embed_ms, "rerank": 0},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
            "rerank": {
                "enabled": bool(rerank_enabled),
                "applied": False,
                "requested_method": rerank_method,
                "method": None,
                "provider": None,
                "model": None,
                "top_k": int(rerank_top_k),
                "hybrid_alpha": float(rerank_hybrid_alpha),
                "hybrid_applied": False,
                "after_rerank": [],
                "reason": "chroma_unavailable",
                "error_type": None,
                "before": [],
                "after": [],
                "timing_ms": 0,
                "errors": [],
            },
            "kbs": {
                "selected": selected_kb_ids,
                "weights": weights_by_kb,
                "orders": orders_by_kb,
                "priority_groups": priority_groups_by_kb,
                "merge": {"mode": "none", "reason": "no_collections"},
                "per_kb": per_kb,
            },
        }
        if pgvector_error:
            out["fallback"] = {"from": "pgvector", "to": "chroma", "error": pgvector_error}
        return out

    rrf_k = int(settings.vector_hybrid_rrf_k or 60)
    priority_enabled = bool(getattr(settings, "vector_priority_retrieval_enabled", False))
    candidates, merge_obs = _merge_kb_candidates(
        kb_ids=selected_kb_ids,
        per_kb_candidates=per_kb_candidates,
        kb_weights=weights_by_kb,
        kb_orders=orders_by_kb,
        kb_priority_groups=priority_groups_by_kb,
        top_k=top_k,
        priority_enabled=priority_enabled,
        rrf_k=rrf_k,
    )

    trimmed_candidates = candidates[:top_k]
    if not rerank_enabled:
        before_ids = [str(c.get("id") or "") for c in trimmed_candidates if isinstance(c, dict)]
        rerank_obs = {
            "enabled": False,
            "applied": False,
            "requested_method": rerank_method,
            "method": None,
            "provider": None,
            "model": None,
            "top_k": int(rerank_top_k),
            "hybrid_alpha": float(rerank_hybrid_alpha),
            "hybrid_applied": False,
            "after_rerank": list(before_ids),
            "reason": "disabled",
            "error_type": None,
            "before": before_ids,
            "after": list(before_ids),
            "timing_ms": 0,
            "errors": [],
        }
    elif trimmed_candidates:
        trimmed_candidates, rerank_obs = _rerank_candidates(
            query_text=query_text,
            candidates=trimmed_candidates,
            method=rerank_method,
            top_k=rerank_top_k,
            hybrid_alpha=rerank_hybrid_alpha,
            external=rerank_external,
        )
    else:
        rerank_obs = {
            "enabled": True,
            "applied": False,
            "requested_method": rerank_method,
            "method": None,
            "provider": None,
            "model": None,
            "top_k": int(rerank_top_k),
            "hybrid_alpha": float(rerank_hybrid_alpha),
            "hybrid_applied": False,
            "after_rerank": [],
            "reason": "empty_candidates",
            "error_type": None,
            "before": [],
            "after": [],
            "timing_ms": 0,
            "errors": [],
        }

    dropped: list[dict[str, Any]] = []
    final_chunks: list[dict[str, Any]] = []
    seen_chunk_keys: set[tuple[str, str, int]] = set()
    selected_by_source: dict[tuple[str, str], int] = {}
    max_chunks = int(settings.vector_final_max_chunks or 6)
    max_chunks = max(1, min(int(max_chunks), 1000))
    per_source_max_chunks = int(getattr(settings, "vector_per_source_id_max_chunks", 1) or 1)
    per_source_max_chunks = max(1, min(int(per_source_max_chunks), 1000))
    processed = 0
    for c in trimmed_candidates:
        processed += 1
        source_key = _vector_candidate_key(c)
        chunk_key = _vector_candidate_chunk_key(c)
        if chunk_key in seen_chunk_keys:
            dropped.append({"id": c.get("id"), "reason": "duplicate_chunk"})
            continue
        seen_chunk_keys.add(chunk_key)
        if selected_by_source.get(source_key, 0) >= per_source_max_chunks:
            dropped.append({"id": c.get("id"), "reason": "per_source_budget"})
            continue
        final_chunks.append(c)
        selected_by_source[source_key] = selected_by_source.get(source_key, 0) + 1
        if len(final_chunks) >= max_chunks:
            break

    if len(final_chunks) >= max_chunks:
        for c in trimmed_candidates[processed:]:
            dropped.append({"id": c.get("id"), "reason": "budget"})

    final_chunks, super_sort_obs = _super_sort_final_chunks(final_chunks, super_sort=super_sort)

    final_char_limit = int(settings.vector_final_char_limit or 6000)
    post_start = time.perf_counter()
    text_md, truncated = _format_final_text(final_chunks, char_limit=final_char_limit)
    post_ms = int((time.perf_counter() - post_start) * 1000)

    timings_ms = {"embed": embed_ms, "query": query_ms, "post": post_ms, "rerank": int(rerank_obs.get("timing_ms") or 0)}
    obs_counts = _build_vector_query_counts(
        candidates_total=len(candidates),
        returned_candidates=trimmed_candidates,
        final_selected=len(final_chunks),
        dropped=dropped,
    )
    budget_obs = _vector_budget_observability(
        top_k=top_k,
        max_chunks=max_chunks,
        per_source_max_chunks=per_source_max_chunks,
        char_limit=final_char_limit,
        dropped=dropped,
    )
    log_event(
        logger,
        "info",
        event="VECTOR_RAG",
        action="query",
        project_id=project_id,
        backend="chroma",
        query_chars=len(query_text or ""),
        candidates=[c.get("id") for c in trimmed_candidates[: min(5, len(trimmed_candidates))]],
        dropped=dropped[:5],
        timings_ms=timings_ms,
        filters={"sources": sources},
        rerank=rerank_obs,
        super_sort=super_sort_obs,
    )

    out: dict[str, Any] = {
        "enabled": True,
        "disabled_reason": None,
        "query_text": query_text,
        "filters": {"project_id": project_id, "sources": sources},
        "timings_ms": timings_ms,
        "candidates": trimmed_candidates,
        "final": {"chunks": final_chunks, "text_md": text_md, "truncated": truncated},
        "dropped": dropped,
        "counts": obs_counts,
        "budget_observability": budget_obs,
        "rerank": rerank_obs,
        "super_sort": super_sort_obs,
        "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": text_md},
        "backend": "chroma",
        "kbs": {
            "selected": selected_kb_ids,
            "weights": weights_by_kb,
            "orders": orders_by_kb,
            "priority_groups": priority_groups_by_kb,
            "merge": merge_obs,
            "per_kb": per_kb,
        },
    }
    if pgvector_error:
        out["fallback"] = {"from": "pgvector", "to": "chroma", "error": pgvector_error}
    return out
