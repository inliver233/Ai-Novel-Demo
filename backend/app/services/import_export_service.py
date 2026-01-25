from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from sqlalchemy import delete

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.utils import new_id
from app.models.project_source_document import ProjectSourceDocument, ProjectSourceDocumentChunk
from app.models.project_settings import ProjectSettings
from app.services.vector_embedding_overrides import vector_embedding_overrides
from app.services.vector_rag_service import VectorChunk, ingest_chunks, purge_project_vectors


_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]{2,}")


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


def _base_filename(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "import"
    if "." in raw:
        raw = raw.rsplit(".", 1)[0]
    raw = raw.strip()
    return raw[:80] if raw else "import"


def _extract_keywords(text: str, *, limit: int) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "") if t]
    if not tokens:
        return []
    counts = Counter(tokens)
    out: list[str] = []
    for token, _ in counts.most_common(max(1, int(limit)) * 3):
        if len(out) >= int(limit):
            break
        if token in {"the", "and", "that", "with", "this", "from", "were", "have", "has"}:
            continue
        out.append(token[:64])
    return out


def _build_worldbook_proposal(*, filename: str, content_text: str) -> dict[str, Any]:
    title = _base_filename(filename)[:255]
    summary = (content_text or "").strip()
    if len(summary) > 5000:
        summary = summary[:5000].rstrip() + "…"
    keywords = _extract_keywords(f"{filename}\n{content_text}", limit=12)

    entry = {
        "title": title,
        "content_md": f"## 导入摘要\n\n{summary}".strip(),
        "enabled": True,
        "constant": False,
        "keywords": keywords,
        "exclude_recursion": False,
        "prevent_recursion": False,
        "char_limit": 12000,
        "priority": "important",
    }
    return {"schema_version": "worldbook_export_all_v1", "entries": [entry]}


def _build_story_memory_proposal(*, filename: str, content_text: str) -> dict[str, Any]:
    title = _base_filename(filename)[:255]
    summary = (content_text or "").strip()
    if len(summary) > 800:
        summary = summary[:800].rstrip() + "…"
    return {
        "schema_version": "story_memory_import_v1",
        "memories": [
            {
                "memory_type": "import_summary",
                "title": title,
                "content": summary,
                "importance_score": 0.6,
                "story_timeline": 0,
                "is_foreshadow": 0,
            }
        ],
    }


def run_import_task(task_id: str) -> None:
    """
    ProjectSourceDocument import worker.

    The task_id is the ProjectSourceDocument.id (so it can be scheduled via TaskQueue without a separate task table).
    """

    doc_id = str(task_id or "").strip()
    if not doc_id:
        return

    db = SessionLocal()
    try:
        doc = db.get(ProjectSourceDocument, doc_id)
        if doc is None:
            return

        project_id = str(doc.project_id)
        filename = str(doc.filename or "").strip()
        content_text = str(doc.content_text or "")

        doc.status = "running"
        doc.progress = 0
        doc.progress_message = "切分文本..."
        doc.error_message = None
        db.commit()

        chunk_size = int(getattr(settings, "vector_chunk_size", 800) or 800)
        overlap = int(getattr(settings, "vector_chunk_overlap", 120) or 120)
        chunks = _chunk_text(content_text, chunk_size=chunk_size, overlap=overlap)

        db.execute(delete(ProjectSourceDocumentChunk).where(ProjectSourceDocumentChunk.document_id == doc_id))
        db.flush()

        rows: list[ProjectSourceDocumentChunk] = []
        vector_chunks: list[VectorChunk] = []
        for idx, chunk in enumerate(chunks):
            vector_chunk_id = f"source_doc:{doc_id}:{idx}"
            rows.append(
                ProjectSourceDocumentChunk(
                    id=new_id(),
                    document_id=doc_id,
                    chunk_index=int(idx),
                    content_text=chunk,
                    vector_chunk_id=vector_chunk_id,
                )
            )
            vector_chunks.append(
                VectorChunk(
                    id=vector_chunk_id,
                    text=chunk,
                    metadata={
                        "project_id": project_id,
                        # NOTE: reuse existing VectorSource label to avoid protocol breakage.
                        "source": "chapter",
                        "source_id": doc_id,
                        "title": filename,
                        "chunk_index": int(idx),
                    },
                )
            )

        if rows:
            db.add_all(rows)

        doc.chunk_count = int(len(chunks))
        doc.progress = 35
        doc.progress_message = f"已切分 {len(chunks)} 个 chunk"

        worldbook_proposal = _build_worldbook_proposal(filename=filename, content_text=content_text)
        story_memory_proposal = _build_story_memory_proposal(filename=filename, content_text=content_text)
        doc.worldbook_proposal_json = json.dumps(worldbook_proposal, ensure_ascii=False)
        doc.story_memory_proposal_json = json.dumps(story_memory_proposal, ensure_ascii=False)

        embedding = vector_embedding_overrides(db.get(ProjectSettings, project_id))
        kb_id = str(doc.kb_id or "").strip() or None

        db.commit()
    except Exception as exc:
        try:
            doc = db.get(ProjectSourceDocument, doc_id)
            if doc is not None:
                doc.status = "failed"
                doc.progress_message = "导入失败"
                doc.error_message = f"{type(exc).__name__}"
                db.commit()
        except Exception:
            pass
        return
    finally:
        db.close()

    # external calls (embedding/vector) must happen without holding DB transactions.
    ingest_result: dict[str, Any] = {}
    try:
        ingest_result = ingest_chunks(project_id=project_id, kb_id=kb_id, chunks=vector_chunks, embedding=embedding)
    except Exception as exc:
        ingest_result = {"enabled": False, "skipped": True, "disabled_reason": "error", "error_type": type(exc).__name__}

    db2 = SessionLocal()
    try:
        doc2 = db2.get(ProjectSourceDocument, doc_id)
        if doc2 is None:
            return
        doc2.vector_ingest_result_json = json.dumps(ingest_result, ensure_ascii=False)
        doc2.progress = 100
        doc2.progress_message = "完成"
        doc2.status = "done"
        db2.commit()
    finally:
        db2.close()


def retry_import_task(*, project_id: str, document_id: str) -> dict[str, Any]:
    """
    Best-effort cleanup for retries:
    - delete previous chunks
    - purge vectors for the document kb_id (if any)
    """

    doc_id = str(document_id or "").strip()
    if not doc_id:
        return {"ok": False, "reason": "document_id_missing"}

    kb_id: str | None = None
    db = SessionLocal()
    try:
        doc = db.get(ProjectSourceDocument, doc_id)
        if doc is None or str(doc.project_id) != str(project_id):
            return {"ok": False, "reason": "not_found"}
        kb_id = str(doc.kb_id or "").strip() or None

        doc.status = "queued"
        doc.progress = 0
        doc.progress_message = "queued"
        doc.error_message = None
        doc.vector_ingest_result_json = None
        db.execute(delete(ProjectSourceDocumentChunk).where(ProjectSourceDocumentChunk.document_id == doc_id))
        db.commit()
    finally:
        db.close()

    purge_out: dict[str, Any] = {}
    if kb_id:
        try:
            purge_out = purge_project_vectors(project_id=str(project_id), kb_id=kb_id)
        except Exception as exc:
            purge_out = {"enabled": True, "skipped": True, "deleted": False, "error_type": type(exc).__name__}

    return {"ok": True, "purge": purge_out, "kb_id": kb_id}
