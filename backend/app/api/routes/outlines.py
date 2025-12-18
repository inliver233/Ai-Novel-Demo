from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sqlalchemy import delete, func, select

from app.api.deps import DbDep, UserIdDep, require_owned_outline, require_owned_project
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.schemas.outline import OutlineCreate, OutlineListItem, OutlineOut, OutlineUpdate

router = APIRouter()


def _parse_structure(value: str | None) -> object | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _outline_out(row: Outline) -> dict:
    return OutlineOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=row.content_md or "",
        structure=_parse_structure(row.structure_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


@router.get("/projects/{project_id}/outlines")
def list_outlines(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    rows = (
        db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.updated_at.desc()))
        .scalars()
        .all()
    )
    counts = dict(
        db.execute(
            select(Chapter.outline_id, func.count(Chapter.id)).where(Chapter.project_id == project_id).group_by(Chapter.outline_id)
        ).all()
    )
    items = [
        OutlineListItem(
            id=r.id,
            title=r.title,
            created_at=r.created_at,
            updated_at=r.updated_at,
            has_chapters=bool(counts.get(r.id, 0)),
        ).model_dump()
        for r in rows
    ]
    return ok_payload(request_id=request_id, data={"outlines": items})


@router.post("/projects/{project_id}/outlines")
def create_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: OutlineCreate) -> dict:
    request_id = request.state.request_id
    project = require_owned_project(db, project_id=project_id, user_id=user_id)

    row = Outline(
        id=new_id(),
        project_id=project_id,
        title=body.title,
        content_md=body.content_md or "",
        structure_json=json.dumps(body.structure, ensure_ascii=False) if body.structure is not None else None,
    )
    db.add(row)
    project.active_outline_id = row.id
    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"outline": _outline_out(row)})


@router.get("/projects/{project_id}/outlines/{outline_id}")
def get_outline_item(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, outline_id: str) -> dict:
    request_id = request.state.request_id
    row = require_owned_outline(db, outline_id=outline_id, user_id=user_id)
    if row.project_id != project_id:
        raise AppError.not_found()
    return ok_payload(request_id=request_id, data={"outline": _outline_out(row)})


@router.put("/projects/{project_id}/outlines/{outline_id}")
def update_outline_item(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    outline_id: str,
    body: OutlineUpdate,
) -> dict:
    request_id = request.state.request_id
    row = require_owned_outline(db, outline_id=outline_id, user_id=user_id)
    if row.project_id != project_id:
        raise AppError.not_found()

    if body.title is not None:
        row.title = body.title
    if body.content_md is not None:
        row.content_md = body.content_md
    if body.structure is not None:
        row.structure_json = json.dumps(body.structure, ensure_ascii=False)

    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"outline": _outline_out(row)})


@router.delete("/projects/{project_id}/outlines/{outline_id}")
def delete_outline_item(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, outline_id: str) -> dict:
    request_id = request.state.request_id
    project = require_owned_project(db, project_id=project_id, user_id=user_id)
    row = require_owned_outline(db, outline_id=outline_id, user_id=user_id)
    if row.project_id != project_id:
        raise AppError.not_found()

    db.execute(delete(Chapter).where(Chapter.outline_id == outline_id))
    db.delete(row)

    if project.active_outline_id == outline_id:
        next_outline = (
            db.execute(
                select(Outline)
                .where(Outline.project_id == project_id, Outline.id != outline_id)
                .order_by(Outline.updated_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        project.active_outline_id = next_outline.id if next_outline else None

    db.commit()
    return ok_payload(request_id=request_id, data={})
