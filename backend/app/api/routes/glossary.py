from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.models.glossary_term import GlossaryTerm
from app.services.glossary_service import rebuild_project_glossary

router = APIRouter()


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
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _safe_json_sources(raw: str | None) -> list[dict[str, object]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            st = str(item.get("source_type") or "").strip()
            sid = str(item.get("source_id") or "").strip()
            if not st or not sid:
                continue
            label = item.get("label")
            out.append({"source_type": st, "source_id": sid, "label": str(label).strip() if isinstance(label, str) and label.strip() else None})
    return out


def _term_public(row: GlossaryTerm) -> dict[str, object]:
    created_at = getattr(row, "created_at", None)
    updated_at = getattr(row, "updated_at", None)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "term": row.term,
        "aliases": _safe_json_list(row.aliases_json),
        "sources": _safe_json_sources(row.sources_json),
        "origin": row.origin,
        "enabled": int(row.enabled or 0),
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


class GlossaryTermCreateRequest(BaseModel):
    term: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    enabled: int = Field(default=1, ge=0, le=1)


class GlossaryTermUpdateRequest(BaseModel):
    term: str | None = Field(default=None, max_length=255)
    aliases: list[str] | None = Field(default=None, max_length=50)
    enabled: int | None = Field(default=None, ge=0, le=1)


class GlossaryRebuildRequest(BaseModel):
    include_chapters: bool = True
    include_imports: bool = True
    max_terms_per_source: int = Field(default=60, ge=1, le=200)


@router.get("/projects/{project_id}/glossary_terms")
def list_glossary_terms(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=80, ge=1, le=300),
    include_disabled: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    q_norm = str(q or "").strip()
    query = select(GlossaryTerm).where(GlossaryTerm.project_id == project_id)
    if not include_disabled:
        query = query.where(GlossaryTerm.enabled == 1)  # noqa: E712
    if q_norm:
        pattern = f"%{q_norm}%"
        query = query.where(or_(GlossaryTerm.term.like(pattern), GlossaryTerm.aliases_json.like(pattern)))
    rows = db.execute(query.order_by(GlossaryTerm.updated_at.desc(), GlossaryTerm.term.asc()).limit(int(limit))).scalars().all()
    return ok_payload(request_id=request_id, data={"terms": [_term_public(r) for r in rows], "returned": len(rows)})


@router.get("/projects/{project_id}/glossary_terms/export_all")
def export_all_glossary_terms(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    rows = db.execute(select(GlossaryTerm).where(GlossaryTerm.project_id == project_id).order_by(GlossaryTerm.term.asc())).scalars().all()
    export_obj = {
        "schema_version": "glossary_export_all_v1",
        "terms": [
            {
                "term": str(r.term or "").strip(),
                "aliases": _safe_json_list(r.aliases_json),
                "origin": str(r.origin or "manual"),
                "enabled": int(r.enabled or 0),
                "sources": _safe_json_sources(r.sources_json),
            }
            for r in rows
        ],
    }
    return ok_payload(request_id=request_id, data={"export": export_obj})


@router.post("/projects/{project_id}/glossary_terms")
def create_glossary_term(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: GlossaryTermCreateRequest) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    term = str(body.term or "").strip()
    if not term:
        raise AppError.validation(details={"reason": "term_missing"})

    existing = (
        db.execute(select(GlossaryTerm).where(GlossaryTerm.project_id == project_id, GlossaryTerm.term == term).limit(1))
        .scalars()
        .first()
    )
    if existing is not None:
        raise AppError.conflict(details={"reason": "term_exists", "term": term})

    aliases = [str(a or "").strip() for a in (body.aliases or []) if isinstance(a, str) and str(a or "").strip()]
    aliases = sorted(dict.fromkeys(aliases))[:50]

    row = GlossaryTerm(
        id=new_id(),
        project_id=project_id,
        term=term,
        aliases_json=json.dumps(aliases, ensure_ascii=False),
        sources_json="[]",
        origin="manual",
        enabled=int(body.enabled or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"term": _term_public(row)})


@router.put("/projects/{project_id}/glossary_terms/{term_id}")
def update_glossary_term(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    term_id: str,
    body: GlossaryTermUpdateRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    row = db.get(GlossaryTerm, str(term_id or "").strip())
    if row is None or str(row.project_id) != str(project_id):
        raise AppError.not_found()

    if body.term is not None:
        next_term = str(body.term or "").strip()
        if not next_term:
            raise AppError.validation(details={"reason": "term_missing"})
        if next_term != str(row.term or ""):
            dup = (
                db.execute(select(GlossaryTerm).where(GlossaryTerm.project_id == project_id, GlossaryTerm.term == next_term).limit(1))
                .scalars()
                .first()
            )
            if dup is not None:
                raise AppError.conflict(details={"reason": "term_exists", "term": next_term})
            row.term = next_term

    if body.aliases is not None:
        aliases = [str(a or "").strip() for a in (body.aliases or []) if isinstance(a, str) and str(a or "").strip()]
        aliases = sorted(dict.fromkeys(aliases))[:50]
        row.aliases_json = json.dumps(aliases, ensure_ascii=False)

    if body.enabled is not None:
        row.enabled = int(body.enabled or 0)

    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"term": _term_public(row)})


@router.delete("/projects/{project_id}/glossary_terms/{term_id}")
def delete_glossary_term(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, term_id: str) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    row = db.get(GlossaryTerm, str(term_id or "").strip())
    if row is None or str(row.project_id) != str(project_id):
        raise AppError.not_found()

    db.delete(row)
    db.commit()
    return ok_payload(request_id=request_id, data={"deleted": True, "id": str(term_id or "").strip()})


@router.post("/projects/{project_id}/glossary_terms/rebuild")
def rebuild_glossary_terms(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: GlossaryRebuildRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    out = rebuild_project_glossary(
        db=db,
        project_id=project_id,
        include_chapters=bool(body.include_chapters),
        include_imports=bool(body.include_imports),
        max_terms_per_source=int(body.max_terms_per_source),
    )
    return ok_payload(request_id=request_id, data=out)

