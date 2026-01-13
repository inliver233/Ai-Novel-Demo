from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import log_event
from app.db.session import SessionLocal, engine
from app.llm.http_client import get_llm_http_client
from app.llm.utils import normalize_base_url
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.worldbook_entry import WorldBookEntry

logger = logging.getLogger("ainovel")

VectorSource = Literal["worldbook", "outline", "chapter"]


@dataclass(frozen=True, slots=True)
class VectorChunk:
    id: str
    text: str
    metadata: dict[str, Any]


_ALL_SOURCES: list[VectorSource] = ["worldbook", "outline", "chapter"]
_PGVECTOR_TABLE = "vector_chunks"


def _is_postgres() -> bool:
    return getattr(getattr(engine, "dialect", None), "name", "") == "postgresql"


def _prefer_pgvector() -> bool:
    backend = str(getattr(settings, "vector_backend", "auto") or "auto").strip().lower()
    if backend == "chroma":
        return False
    if backend == "pgvector":
        return _is_postgres()
    return _is_postgres()


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
    *, query_text: str, candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before = [str(c.get("id") or "") for c in candidates if isinstance(c, dict)]
    start = time.perf_counter()

    qtext = (query_text or "").strip()
    if not qtext or not candidates:
        return list(candidates), {
            "enabled": True,
            "applied": False,
            "method": None,
            "reason": "empty_query_or_candidates",
            "before": before,
            "after": list(before),
            "timing_ms": int((time.perf_counter() - start) * 1000),
        }

    errors: list[dict[str, str]] = []
    for method in ("rapidfuzz_token_set_ratio", "token_overlap"):
        try:
            scored: list[tuple[float, int, dict[str, Any]]] = []
            for idx, c in enumerate(candidates):
                if not isinstance(c, dict):
                    continue
                score = float(_rerank_score(method=method, query_text=qtext, candidate_text=str(c.get("text") or "")))
                scored.append((score, idx, c))

            scored.sort(key=lambda x: (-x[0], x[1]))
            reranked = [c for _score, _idx, c in scored]
            after = [str(c.get("id") or "") for c in reranked if isinstance(c, dict)]
            obs: dict[str, Any] = {
                "enabled": True,
                "applied": True,
                "method": method,
                "before": before,
                "after": after,
                "timing_ms": int((time.perf_counter() - start) * 1000),
            }
            if errors:
                obs["fallback"] = errors
            return reranked, obs
        except ImportError as exc:
            errors.append({"method": method, "reason": "dependency_missing", "error": type(exc).__name__})
        except Exception as exc:
            errors.append({"method": method, "reason": "error", "error": type(exc).__name__})

    return list(candidates), {
        "enabled": True,
        "applied": False,
        "method": None,
        "before": before,
        "after": list(before),
        "timing_ms": int((time.perf_counter() - start) * 1000),
        "errors": errors,
    }


def _vector_candidate_key(candidate: dict[str, Any]) -> tuple[str, str]:
    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    return (str(meta.get("source") or ""), str(meta.get("source_id") or ""))


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


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_chroma_persist_dir() -> str:
    return str((_backend_dir() / ".chroma").resolve().as_posix())


def _resolve_embedding_values(embedding: dict[str, str | None] | None) -> tuple[str | None, str | None, str | None]:
    if not embedding:
        return settings.vector_embedding_base_url, settings.vector_embedding_model, settings.vector_embedding_api_key
    return (
        (embedding.get("base_url") or settings.vector_embedding_base_url),
        (embedding.get("model") or settings.vector_embedding_model),
        (embedding.get("api_key") or settings.vector_embedding_api_key),
    )


def _vector_enabled_reason(*, embedding: dict[str, str | None] | None = None) -> tuple[bool, str | None]:
    base_url, model, api_key = _resolve_embedding_values(embedding)
    if not base_url:
        return False, "embedding_base_url_missing"
    if not model:
        return False, "embedding_model_missing"
    if not api_key:
        return False, "embedding_api_key_missing"
    return True, None


def vector_rag_status(
    *,
    project_id: str,
    sources: list[VectorSource] | None = None,
    embedding: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    sources = sources or list(_ALL_SOURCES)
    enabled, disabled_reason = _vector_enabled_reason(embedding=embedding)
    if not enabled:
        return {
            "enabled": False,
            "disabled_reason": disabled_reason,
            "query_text": "",
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
            "backend_preferred": "pgvector" if _prefer_pgvector() else "chroma",
            "hybrid_enabled": bool(getattr(settings, "vector_hybrid_enabled", True)),
        }
    return {
        "enabled": True,
        "disabled_reason": None,
        "query_text": "",
        "filters": {"project_id": project_id, "sources": sources},
        "timings_ms": {},
        "candidates": [],
        "final": {"chunks": [], "text_md": "", "truncated": False},
        "dropped": [],
        "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
        "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
        "backend_preferred": "pgvector" if _prefer_pgvector() else "chroma",
        "hybrid_enabled": bool(getattr(settings, "vector_hybrid_enabled", True)),
    }


def _import_chromadb() -> Any:
    try:
        import chromadb  # type: ignore[import-not-found]

        return chromadb
    except Exception as exc:  # pragma: no cover - env dependent
        raise RuntimeError("chromadb is not installed") from exc


def _sanitize_collection_name(project_id: str) -> str:
    raw = f"ainovel_{project_id}"
    safe = re.sub(r"[^A-Za-z0-9_\\-]+", "_", raw).strip("_")
    if not safe:
        safe = "ainovel_default"
    return safe[:60]


def _get_collection(*, project_id: str):
    chromadb = _import_chromadb()
    persist_dir = settings.vector_chroma_persist_dir or _default_chroma_persist_dir()
    client = chromadb.PersistentClient(path=persist_dir)
    name = _sanitize_collection_name(project_id)
    return client.get_or_create_collection(name=name, metadata={"project_id": project_id})


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
    sources = sources or ["worldbook", "outline", "chapter"]
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

    return out


def _embed_texts(texts: list[str], *, embedding: dict[str, str | None] | None = None) -> list[list[float]]:
    base_url_raw, model_raw, api_key_raw = _resolve_embedding_values(embedding)
    base_url = normalize_base_url(str(base_url_raw or ""))
    model = str(model_raw or "")
    api_key = str(api_key_raw or "")

    url = base_url.rstrip("/") + "/embeddings"
    client = get_llm_http_client()
    resp = client.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": texts},
        timeout=60.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("bad embeddings response: missing data")

    vectors: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        emb = item.get("embedding")
        if not isinstance(emb, list):
            continue
        vec = [float(x) for x in emb]
        vectors.append(vec)

    if len(vectors) != len(texts):
        raise RuntimeError("bad embeddings response: length mismatch")
    return vectors


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
        embeddings = _embed_texts(texts, embedding=embedding)

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
        collection = _get_collection(project_id=project_id)
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
        out = ingest_chunks(project_id=project_id, chunks=chunks, embedding=embedding)
        return {"enabled": bool(out.get("enabled")), "skipped": bool(out.get("skipped")), "rebuilt": int(out.get("ingested") or 0), **out}

    try:
        chromadb = _import_chromadb()
        persist_dir = settings.vector_chroma_persist_dir or _default_chroma_persist_dir()
        client = chromadb.PersistentClient(path=persist_dir)
        name = _sanitize_collection_name(project_id)
        try:
            client.delete_collection(name=name)
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover - env dependent
        return {"enabled": False, "skipped": True, "disabled_reason": "chroma_unavailable", "error": str(exc), "rebuilt": 0}

    out = ingest_chunks(project_id=project_id, chunks=chunks, embedding=embedding)
    return {"enabled": bool(out.get("enabled")), "skipped": bool(out.get("skipped")), "rebuilt": int(out.get("ingested") or 0), **out}


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
    query_text: str,
    sources: list[VectorSource] | None = None,
    embedding: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    sources = sources or list(_ALL_SOURCES)
    enabled, disabled_reason = _vector_enabled_reason(embedding=embedding)
    if not enabled:
        return {
            "enabled": False,
            "disabled_reason": disabled_reason,
            "query_text": query_text,
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
        }

    start = time.perf_counter()
    qvec = _embed_texts([query_text.strip() or " "], embedding=embedding)[0]
    embed_ms = int((time.perf_counter() - start) * 1000)

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
            rerank_obs: dict[str, Any] | None = None
            if bool(getattr(settings, "vector_rerank_enabled", False)) and trimmed_candidates:
                trimmed_candidates, rerank_obs = _rerank_candidates(query_text=query_text, candidates=trimmed_candidates)
            dropped: list[dict[str, Any]] = []
            final_chunks: list[dict[str, Any]] = []
            seen_keys: set[tuple[str, str]] = set()
            max_chunks = int(settings.vector_final_max_chunks or 6)
            processed = 0
            for c in trimmed_candidates:
                processed += 1
                meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
                key = (str(meta.get("source") or ""), str(meta.get("source_id") or ""))
                if key in seen_keys:
                    dropped.append({"id": c.get("id"), "reason": "duplicate_source"})
                    continue
                seen_keys.add(key)
                final_chunks.append(c)
                if len(final_chunks) >= max_chunks:
                    break

            if len(final_chunks) >= max_chunks:
                for c in trimmed_candidates[processed:]:
                    dropped.append({"id": c.get("id"), "reason": "budget"})

            post_start = time.perf_counter()
            text_md, truncated = _format_final_text(final_chunks, char_limit=int(settings.vector_final_char_limit or 6000))
            post_ms = int((time.perf_counter() - post_start) * 1000)

            timings_ms = {"embed": embed_ms, "query": query_ms, "post": post_ms}
            if rerank_obs:
                timings_ms["rerank"] = int(rerank_obs.get("timing_ms") or 0)
            obs_counts = _build_vector_query_counts(
                candidates_total=len(candidates),
                returned_candidates=trimmed_candidates,
                final_selected=len(final_chunks),
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
                "rerank": rerank_obs,
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

    try:
        collection = _get_collection(project_id=project_id)
    except Exception as exc:  # pragma: no cover - env dependent
        out: dict[str, Any] = {
            "enabled": False,
            "disabled_reason": "chroma_unavailable",
            "error": str(exc),
            "query_text": query_text,
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {"embed": embed_ms},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "counts": _build_vector_query_counts(candidates_total=0, returned_candidates=[], final_selected=0, dropped=[]),
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
        }
        if pgvector_error:
            out["fallback"] = {"from": "pgvector", "to": "chroma", "error": pgvector_error}
        return out

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
    query_ms = int((time.perf_counter() - query_start) * 1000)

    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    candidates: list[dict[str, Any]] = []
    for idx in range(min(len(ids), len(docs), len(metas), len(dists))):
        meta = metas[idx] if isinstance(metas[idx], dict) else {}
        if sources and str(meta.get("source") or "") not in sources:
            continue
        candidates.append(
            {
                "id": str(ids[idx]),
                "distance": float(dists[idx]),
                "text": str(docs[idx] or ""),
                "metadata": meta,
            }
        )

    trimmed_candidates = candidates[:top_k]
    rerank_obs: dict[str, Any] | None = None
    if bool(getattr(settings, "vector_rerank_enabled", False)) and trimmed_candidates:
        trimmed_candidates, rerank_obs = _rerank_candidates(query_text=query_text, candidates=trimmed_candidates)

    dropped: list[dict[str, Any]] = []
    final_chunks: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    max_chunks = int(settings.vector_final_max_chunks or 6)
    processed = 0
    for c in trimmed_candidates:
        processed += 1
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        key = (str(meta.get("source") or ""), str(meta.get("source_id") or ""))
        if key in seen_keys:
            dropped.append({"id": c.get("id"), "reason": "duplicate_source"})
            continue
        seen_keys.add(key)
        final_chunks.append(c)
        if len(final_chunks) >= max_chunks:
            break

    if len(final_chunks) >= max_chunks:
        for c in trimmed_candidates[processed:]:
            dropped.append({"id": c.get("id"), "reason": "budget"})

    post_start = time.perf_counter()
    text_md, truncated = _format_final_text(final_chunks, char_limit=int(settings.vector_final_char_limit or 6000))
    post_ms = int((time.perf_counter() - post_start) * 1000)

    timings_ms = {"embed": embed_ms, "query": query_ms, "post": post_ms}
    if rerank_obs:
        timings_ms["rerank"] = int(rerank_obs.get("timing_ms") or 0)
    obs_counts = _build_vector_query_counts(
        candidates_total=len(candidates),
        returned_candidates=trimmed_candidates,
        final_selected=len(final_chunks),
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
        "rerank": rerank_obs,
        "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": text_md},
        "backend": "chroma",
    }
    if pgvector_error:
        out["fallback"] = {"from": "pgvector", "to": "chroma", "error": pgvector_error}
    return out
