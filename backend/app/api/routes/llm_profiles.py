from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select, update

from app.api.deps import DbDep, UserIdDep, require_owned_llm_profile
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.llm.utils import normalize_base_url
from app.models.llm_profile import LLMProfile
from app.models.project import Project
from app.schemas.llm_profiles import LLMProfileCreate, LLMProfileOut, LLMProfileUpdate

router = APIRouter()


def _normalize_profile(provider: str, base_url: str | None) -> str | None:
    if provider == "openai":
        return normalize_base_url(base_url or "https://api.openai.com/v1")
    if provider == "openai_compatible":
        if not base_url:
            raise AppError(code="LLM_CONFIG_ERROR", message="openai_compatible 必须填写 base_url", status_code=400)
        return normalize_base_url(base_url)
    if provider == "anthropic":
        return normalize_base_url(base_url or "https://api.anthropic.com")
    if provider == "gemini":
        return normalize_base_url(base_url or "https://generativelanguage.googleapis.com")
    raise AppError(code="LLM_CONFIG_ERROR", message="不支持的 provider", status_code=400, details={"provider": provider})


def _to_out(row: LLMProfile) -> dict:
    return LLMProfileOut(
        id=row.id,
        owner_user_id=row.owner_user_id,
        name=row.name,
        provider=row.provider,
        base_url=row.base_url,
        model=row.model,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


@router.get("/llm_profiles")
def list_profiles(request: Request, db: DbDep, user_id: UserIdDep) -> dict:
    request_id = request.state.request_id
    rows = (
        db.execute(select(LLMProfile).where(LLMProfile.owner_user_id == user_id).order_by(LLMProfile.updated_at.desc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"profiles": [_to_out(r) for r in rows]})


@router.post("/llm_profiles")
def create_profile(request: Request, db: DbDep, user_id: UserIdDep, body: LLMProfileCreate) -> dict:
    request_id = request.state.request_id
    row = LLMProfile(
        id=new_id(),
        owner_user_id=user_id,
        name=body.name,
        provider=body.provider,
        base_url=_normalize_profile(body.provider, body.base_url),
        model=body.model,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"profile": _to_out(row)})


@router.put("/llm_profiles/{profile_id}")
def update_profile(request: Request, db: DbDep, user_id: UserIdDep, profile_id: str, body: LLMProfileUpdate) -> dict:
    request_id = request.state.request_id
    row = require_owned_llm_profile(db, profile_id=profile_id, user_id=user_id)

    provider = body.provider or row.provider
    base_url = body.base_url if "base_url" in body.model_fields_set else row.base_url
    model = body.model or row.model

    if body.name is not None:
        row.name = body.name
    if body.provider is not None:
        row.provider = body.provider
    if "base_url" in body.model_fields_set:
        row.base_url = body.base_url
    if body.model is not None:
        row.model = body.model

    row.base_url = _normalize_profile(provider, base_url)
    row.model = model

    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"profile": _to_out(row)})


@router.delete("/llm_profiles/{profile_id}")
def delete_profile(request: Request, db: DbDep, user_id: UserIdDep, profile_id: str) -> dict:
    request_id = request.state.request_id
    row = require_owned_llm_profile(db, profile_id=profile_id, user_id=user_id)

    db.execute(update(Project).where(Project.llm_profile_id == profile_id).values(llm_profile_id=None))
    db.delete(row)
    db.commit()
    return ok_payload(request_id=request_id, data={})
