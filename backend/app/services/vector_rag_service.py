from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import log_event
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


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_chroma_persist_dir() -> str:
    return str((_backend_dir() / ".chroma").resolve().as_posix())


def _vector_enabled_reason() -> tuple[bool, str | None]:
    if not settings.vector_embedding_base_url:
        return False, "embedding_base_url_missing"
    if not settings.vector_embedding_model:
        return False, "embedding_model_missing"
    if not settings.vector_embedding_api_key:
        return False, "embedding_api_key_missing"
    return True, None


def vector_rag_status(*, project_id: str, sources: list[VectorSource] | None = None) -> dict[str, Any]:
    sources = sources or ["worldbook", "outline", "chapter"]
    enabled, disabled_reason = _vector_enabled_reason()
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
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
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
        "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
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


def _embed_texts(texts: list[str]) -> list[list[float]]:
    base_url = normalize_base_url(str(settings.vector_embedding_base_url))
    model = str(settings.vector_embedding_model)
    api_key = str(settings.vector_embedding_api_key)

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


def ingest_chunks(*, project_id: str, chunks: list[VectorChunk]) -> dict[str, Any]:
    enabled, disabled_reason = _vector_enabled_reason()
    if not enabled:
        return {"enabled": False, "skipped": True, "disabled_reason": disabled_reason, "ingested": 0}

    try:
        collection = _get_collection(project_id=project_id)
    except Exception as exc:  # pragma: no cover - env dependent
        return {"enabled": False, "skipped": True, "disabled_reason": "chroma_unavailable", "error": str(exc), "ingested": 0}

    start = time.perf_counter()
    texts = [c.text for c in chunks]
    ids = [c.id for c in chunks]
    metadatas = [c.metadata for c in chunks]

    embeddings: list[list[float]] = []
    if texts:
        embeddings = _embed_texts(texts)

    embed_ms = int((time.perf_counter() - start) * 1000)
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
    )
    return {"enabled": True, "skipped": False, "ingested": len(chunks), "timings_ms": {"embed": embed_ms, "upsert": write_ms}}


def rebuild_project(*, project_id: str, chunks: list[VectorChunk]) -> dict[str, Any]:
    enabled, disabled_reason = _vector_enabled_reason()
    if not enabled:
        return {"enabled": False, "skipped": True, "disabled_reason": disabled_reason, "rebuilt": 0}

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

    out = ingest_chunks(project_id=project_id, chunks=chunks)
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
) -> dict[str, Any]:
    sources = sources or ["worldbook", "outline", "chapter"]
    enabled, disabled_reason = _vector_enabled_reason()
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
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
        }

    try:
        collection = _get_collection(project_id=project_id)
    except Exception as exc:  # pragma: no cover - env dependent
        return {
            "enabled": False,
            "disabled_reason": "chroma_unavailable",
            "error": str(exc),
            "query_text": query_text,
            "filters": {"project_id": project_id, "sources": sources},
            "timings_ms": {},
            "candidates": [],
            "final": {"chunks": [], "text_md": "", "truncated": False},
            "dropped": [],
            "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": ""},
        }

    start = time.perf_counter()
    qvec = _embed_texts([query_text.strip() or " "])[0]
    embed_ms = int((time.perf_counter() - start) * 1000)

    query_start = time.perf_counter()
    top_k = int(settings.vector_max_candidates or 20)
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

    dropped: list[dict[str, Any]] = []
    final_chunks: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for c in candidates:
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        key = (str(meta.get("source") or ""), str(meta.get("source_id") or ""))
        if key in seen_keys:
            dropped.append({"id": c.get("id"), "reason": "duplicate_source"})
            continue
        seen_keys.add(key)
        final_chunks.append(c)
        if len(final_chunks) >= int(settings.vector_final_max_chunks or 6):
            break

    trimmed_candidates = candidates[:top_k]
    for c in candidates[len(final_chunks) :]:
        if len(final_chunks) >= int(settings.vector_final_max_chunks or 6):
            dropped.append({"id": c.get("id"), "reason": "budget"})

    post_start = time.perf_counter()
    text_md, truncated = _format_final_text(final_chunks, char_limit=int(settings.vector_final_char_limit or 6000))
    post_ms = int((time.perf_counter() - post_start) * 1000)

    log_event(
        logger,
        "info",
        event="VECTOR_RAG",
        action="query",
        project_id=project_id,
        query_chars=len(query_text or ""),
        candidates=[c.get("id") for c in trimmed_candidates[: min(5, len(trimmed_candidates))]],
        dropped=dropped[:5],
        timings_ms={"embed": embed_ms, "query": query_ms, "post": post_ms},
        filters={"sources": sources},
    )

    return {
        "enabled": True,
        "disabled_reason": None,
        "query_text": query_text,
        "filters": {"project_id": project_id, "sources": sources},
        "timings_ms": {"embed": embed_ms, "query": query_ms, "post": post_ms},
        "candidates": trimmed_candidates,
        "final": {"chunks": final_chunks, "text_md": text_md, "truncated": truncated},
        "dropped": dropped,
        "prompt_block": {"identifier": "sys.memory.vector_rag", "role": "system", "text_md": text_md},
    }
