from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_owned_generation_run, require_owned_project
from app.core.errors import ok_payload
from app.models.generation_run import GenerationRun
from app.schemas.generation_runs import GenerationRunOut

router = APIRouter()


@router.get("/projects/{project_id}/generation_runs")
def list_runs(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    limit: int = Query(default=5, ge=1, le=50),
) -> dict:
    request_id = request.state.request_id
    require_owned_project(db, project_id=project_id, user_id=user_id)
    rows = (
        db.execute(
            select(GenerationRun)
            .where(GenerationRun.project_id == project_id)
            .order_by(GenerationRun.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    def _to_out(r: GenerationRun) -> dict:
        params = {}
        if r.params_json:
            try:
                params = json.loads(r.params_json)
            except Exception:
                params = {"_raw": r.params_json}
        err = None
        if r.error_json:
            try:
                err = json.loads(r.error_json)
            except Exception:
                err = {"_raw": r.error_json}
        return GenerationRunOut(
            id=r.id,
            project_id=r.project_id,
            actor_user_id=r.actor_user_id,
            chapter_id=r.chapter_id,
            type=r.type,
            provider=r.provider,
            model=r.model,
            request_id=r.request_id,
            prompt_system=r.prompt_system,
            prompt_user=r.prompt_user,
            params=params,
            output_text=r.output_text,
            error=err,
            created_at=r.created_at,
        ).model_dump()

    return ok_payload(request_id=request_id, data={"runs": [_to_out(r) for r in rows]})


@router.get("/generation_runs/{run_id}")
def get_run(request: Request, db: DbDep, user_id: UserIdDep, run_id: str) -> dict:
    request_id = request.state.request_id
    row = require_owned_generation_run(db, run_id=run_id, user_id=user_id)
    params = {}
    if row.params_json:
        try:
            params = json.loads(row.params_json)
        except Exception:
            params = {"_raw": row.params_json}
    err = None
    if row.error_json:
        try:
            err = json.loads(row.error_json)
        except Exception:
            err = {"_raw": row.error_json}
    payload = GenerationRunOut(
        id=row.id,
        project_id=row.project_id,
        actor_user_id=row.actor_user_id,
        chapter_id=row.chapter_id,
        type=row.type,
        provider=row.provider,
        model=row.model,
        request_id=row.request_id,
        prompt_system=row.prompt_system,
        prompt_user=row.prompt_user,
        params=params,
        output_text=row.output_text,
        error=err,
        created_at=row.created_at,
    ).model_dump()
    return ok_payload(request_id=request_id, data={"run": payload})

