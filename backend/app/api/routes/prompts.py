from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_owned_project
from app.core.errors import ok_payload
from app.db.utils import new_id
from app.models.prompt_template import PromptTemplate
from app.schemas.prompts import PromptTemplateItem, PromptsPutRequest
from app.services.defaults import default_prompt_templates

router = APIRouter()


def _default_templates() -> list[PromptTemplateItem]:
    return default_prompt_templates()


@router.get("/projects/{project_id}/prompts")
def get_prompts(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    rows = db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    if not rows:
        defaults = _default_templates()
        db.add_all(
            [
                PromptTemplate(
                    id=new_id(),
                    project_id=project_id,
                    type=t.type,
                    system_template=t.system_template,
                    user_template=t.user_template,
                )
                for t in defaults
            ]
        )
        db.commit()
        rows = db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()

    templates = [
        PromptTemplateItem(
            type=r.type,
            system_template=r.system_template,
            user_template=r.user_template,
            updated_at=r.updated_at,
        ).model_dump()
        for r in rows
    ]
    return ok_payload(request_id=request_id, data={"templates": templates})


@router.put("/projects/{project_id}/prompts")
def put_prompts(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: PromptsPutRequest) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)

    existing = {
        r.type: r
        for r in db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    }
    for t in body.templates:
        row = existing.get(t.type)
        if row is None:
            row = PromptTemplate(id=new_id(), project_id=project_id, type=t.type, system_template="", user_template="")
            db.add(row)
        if t.system_template is not None:
            row.system_template = t.system_template
        if t.user_template is not None:
            row.user_template = t.user_template
    db.commit()

    rows = db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    templates = [
        PromptTemplateItem(
            type=r.type,
            system_template=r.system_template,
            user_template=r.user_template,
            updated_at=r.updated_at,
        ).model_dump()
        for r in rows
    ]
    return ok_payload(request_id=request_id, data={"templates": templates})
