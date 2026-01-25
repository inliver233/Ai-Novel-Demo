from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, load_only

from app.core.config import settings
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.project_settings import ProjectSettings
from app.models.project_source_document import ProjectSourceDocument


_TOKEN_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]{2,}")
_PAIR_RE = re.compile(r"([0-9A-Za-z\u4e00-\u9fff]{2,32})[（(]([0-9A-Za-z\u4e00-\u9fff]{2,32})[）)]")
_ASCII_WORD_RE = re.compile(r"^[0-9a-z_]+$")

_EN_STOPWORDS = {
    "the",
    "and",
    "that",
    "with",
    "this",
    "from",
    "were",
    "have",
    "has",
    "into",
    "your",
    "you",
    "for",
    "are",
    "but",
    "not",
    "all",
    "can",
    "will",
    "one",
    "two",
    "three",
}

_CN_STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "她们",
    "但是",
    "因为",
    "所以",
    "如果",
    "一个",
    "这个",
    "那个",
    "以及",
    "然后",
    "同时",
}


def _safe_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s:
            out.append(s)
    return out


def _safe_json_obj_list(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
    return out


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _normalize_token(token: str) -> str:
    s = (token or "").strip()
    if not s:
        return ""
    if _ASCII_WORD_RE.fullmatch(s.lower()):
        return s.lower()
    return s


def extract_glossary_candidates(*, text: str, max_terms: int = 60) -> dict[str, set[str]]:
    """
    Heuristic extractor:
    - term(alias) pairs → record alias
    - frequent tokens → record as standalone terms
    """

    raw = (text or "").strip()
    if not raw:
        return {}

    term_to_aliases: dict[str, set[str]] = {}
    for m in _PAIR_RE.finditer(raw):
        a = _normalize_token(m.group(1) or "")
        b = _normalize_token(m.group(2) or "")
        if not a or not b or a == b:
            continue
        term_to_aliases.setdefault(a, set()).add(b)

    tokens = [_normalize_token(t) for t in _TOKEN_RE.findall(raw)]
    tokens = [t for t in tokens if t and not t.isdigit()]
    if not tokens:
        return term_to_aliases

    counts = Counter(tokens)
    for token, _freq in counts.most_common(int(max_terms) * 3):
        if len(term_to_aliases) >= int(max_terms):
            break
        if token in _EN_STOPWORDS or token in _CN_STOPWORDS:
            continue
        term_to_aliases.setdefault(token, set())

    return term_to_aliases


def _merge_sources(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in list(existing or []) + list(incoming or []):
        st = str(item.get("source_type") or "").strip()
        sid = str(item.get("source_id") or "").strip()
        if not st or not sid:
            continue
        key = (st, sid)
        if key in seen:
            continue
        seen.add(key)
        out.append({"source_type": st, "source_id": sid, "label": str(item.get("label") or "").strip() or None})
    return out


def rebuild_project_glossary(
    *,
    db: Session,
    project_id: str,
    include_chapters: bool = True,
    include_imports: bool = True,
    max_terms_per_source: int = 60,
) -> dict[str, Any]:
    """
    Rebuild auto glossary terms from chapters + import documents.

    Manual terms are preserved. Auto terms are replaced.
    """

    if not project_id:
        return {"ok": False, "reason": "project_id_missing"}

    extracted: dict[str, dict[str, Any]] = {}

    if include_chapters:
        chapter_rows = (
            db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .options(load_only(Chapter.id, Chapter.title, Chapter.content_md, Chapter.updated_at))
                .order_by(Chapter.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for ch in chapter_rows:
            candidates = extract_glossary_candidates(text=str(ch.content_md or ""), max_terms=int(max_terms_per_source))
            if not candidates:
                continue
            src = {"source_type": "chapter", "source_id": str(ch.id), "label": str(ch.title or "").strip() or None}
            for term, aliases in candidates.items():
                slot = extracted.setdefault(term, {"aliases": set(), "sources": []})
                slot["aliases"].update(set(aliases))
                slot["sources"].append(src)

    if include_imports:
        doc_rows = (
            db.execute(
                select(ProjectSourceDocument)
                .where(ProjectSourceDocument.project_id == project_id)
                .options(
                    load_only(
                        ProjectSourceDocument.id,
                        ProjectSourceDocument.filename,
                        ProjectSourceDocument.content_text,
                        ProjectSourceDocument.updated_at,
                    )
                )
                .order_by(ProjectSourceDocument.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for doc in doc_rows:
            candidates = extract_glossary_candidates(text=str(doc.content_text or ""), max_terms=int(max_terms_per_source))
            if not candidates:
                continue
            src = {"source_type": "import", "source_id": str(doc.id), "label": str(doc.filename or "").strip() or None}
            for term, aliases in candidates.items():
                slot = extracted.setdefault(term, {"aliases": set(), "sources": []})
                slot["aliases"].update(set(aliases))
                slot["sources"].append(src)

    existing_rows = (
        db.execute(select(GlossaryTerm).where(GlossaryTerm.project_id == project_id))
        .scalars()
        .all()
    )
    by_term = {str(r.term or ""): r for r in existing_rows}

    # Replace auto terms (manual terms preserved).
    db.execute(delete(GlossaryTerm).where(GlossaryTerm.project_id == project_id, GlossaryTerm.origin == "auto"))
    db.flush()

    created = 0
    updated = 0
    for term, meta in extracted.items():
        term_norm = str(term or "").strip()
        if not term_norm:
            continue
        aliases = sorted({str(a).strip() for a in (meta.get("aliases") or []) if isinstance(a, str) and str(a).strip()})
        sources = _merge_sources([], meta.get("sources") or [])

        existing = by_term.get(term_norm)
        if existing is not None and str(existing.origin or "") == "manual":
            existing_aliases = set(_safe_json_list(existing.aliases_json))
            merged_aliases = sorted({*existing_aliases, *aliases})
            existing.aliases_json = _compact_json_dumps(merged_aliases)
            existing.sources_json = _compact_json_dumps(_merge_sources(_safe_json_obj_list(existing.sources_json), sources))
            updated += 1
            continue

        db.add(
            GlossaryTerm(
                id=new_id(),
                project_id=project_id,
                term=term_norm,
                aliases_json=_compact_json_dumps(aliases),
                sources_json=_compact_json_dumps(sources),
                origin="auto",
                enabled=1,
            )
        )
        created += 1

    settings_row = db.get(ProjectSettings, project_id)
    if settings_row is None:
        settings_row = ProjectSettings(project_id=project_id)
        db.add(settings_row)
    settings_row.vector_index_dirty = True

    db.commit()
    return {"ok": True, "created": created, "updated": updated, "terms": len(extracted)}


def _ascii_word_boundary_contains(*, haystack: str, needle: str) -> bool:
    if not needle:
        return False
    pattern = r"(?<![0-9a-z_])" + re.escape(needle) + r"(?![0-9a-z_])"
    return re.search(pattern, haystack) is not None


def expand_query_text_with_glossary(
    *,
    db: Session,
    project_id: str,
    query_text: str,
) -> tuple[str, dict[str, Any]]:
    enabled = bool(getattr(settings, "glossary_query_expand_enabled", False))
    obs: dict[str, Any] = {"enabled": enabled, "matched": [], "added_terms": []}
    if not enabled:
        return query_text, obs

    q = (query_text or "").strip()
    if not q:
        return q, obs

    try:
        rows = (
            db.execute(
                select(GlossaryTerm)
                .where(GlossaryTerm.project_id == project_id)
                .where(GlossaryTerm.enabled == 1)  # noqa: E712
            )
            .scalars()
            .all()
        )
    except Exception as exc:
        obs["error"] = type(exc).__name__
        return q, obs

    q_lower = q.lower()
    added: list[str] = []
    matched: list[dict[str, str]] = []

    for row in rows:
        term = str(row.term or "").strip()
        if not term:
            continue
        aliases = _safe_json_list(row.aliases_json)
        for alias in aliases:
            alias_norm = str(alias or "").strip()
            if not alias_norm:
                continue
            alias_lower = alias_norm.lower()
            hit = (
                _ascii_word_boundary_contains(haystack=q_lower, needle=alias_lower)
                if _ASCII_WORD_RE.fullmatch(alias_lower)
                else alias_lower in q_lower
            )
            if not hit:
                continue
            matched.append({"alias": alias_norm, "term": term})
            if term.lower() not in q_lower:
                added.append(term)
            break

    # de-dup, bounded.
    uniq_added: list[str] = []
    seen: set[str] = set()
    for t in added:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_added.append(t)
        if len(uniq_added) >= 8:
            break

    obs["matched"] = matched[:16]
    obs["added_terms"] = uniq_added
    if not uniq_added:
        return q, obs
    expanded = f"{q} {' '.join(uniq_added)}"
    return expanded, obs
