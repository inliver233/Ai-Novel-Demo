from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select, update

from app.api.deps import DbDep, UserIdDep, require_owned_llm_profile
from app.core.errors import AppError, ok_payload
from app.core.secrets import SecretCryptoError, encrypt_secret, mask_api_key
from app.db.utils import new_id
from app.llm.utils import default_max_tokens, normalize_base_url
from app.models.llm_preset import LLMPreset
from app.models.llm_profile import LLMProfile
from app.models.project import Project
from app.schemas.llm_profiles import LLMProfileCreate, LLMProfileOut, LLMProfileUpdate

router = APIRouter()


def _normalize_profile(provider: str, base_url: str | None) -> str | None:
    if provider in ("openai", "openai_responses"):
        return normalize_base_url(base_url or "https://api.openai.com/v1")
    if provider in ("openai_compatible", "openai_responses_compatible"):
        if not base_url:
            raise AppError(code="LLM_CONFIG_ERROR", message=f"{provider} 必须填写 base_url", status_code=400)
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
        has_api_key=bool(row.api_key_ciphertext),
        masked_api_key=row.api_key_masked,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


def _sync_bound_project_presets(db: DbDep, profile: LLMProfile) -> None:
    project_ids = db.execute(select(Project.id).where(Project.llm_profile_id == profile.id)).scalars().all()
    if not project_ids:
        return

    base_url = _normalize_profile(profile.provider, profile.base_url)
    for project_id in project_ids:
        preset = db.get(LLMPreset, project_id)
        if preset is None:
            preset = LLMPreset(
                project_id=project_id,
                provider=profile.provider,
                base_url=base_url,
                model=profile.model,
                temperature=0.7,
                top_p=1.0,
                max_tokens=default_max_tokens(profile.provider, profile.model),
                presence_penalty=0.0,
                frequency_penalty=0.0,
                top_k=None,
                stop_json="[]",
                timeout_seconds=180,
                extra_json="{}",
            )
            db.add(preset)
            continue

        preset.provider = profile.provider
        preset.base_url = base_url
        preset.model = profile.model


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
    if body.api_key is not None:
        key = body.api_key.strip()
        if key:
            try:
                row.api_key_ciphertext = encrypt_secret(key)
            except SecretCryptoError:
                raise AppError(code="SECRET_CONFIG_ERROR", message="服务端未配置 SECRET_ENCRYPTION_KEY", status_code=500)
            row.api_key_masked = mask_api_key(key)
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

    if "api_key" in body.model_fields_set:
        key = (body.api_key or "").strip()
        if key:
            try:
                row.api_key_ciphertext = encrypt_secret(key)
            except SecretCryptoError:
                raise AppError(code="SECRET_CONFIG_ERROR", message="服务端未配置 SECRET_ENCRYPTION_KEY", status_code=500)
            row.api_key_masked = mask_api_key(key)
        else:
            row.api_key_ciphertext = None
            row.api_key_masked = None

    row.base_url = _normalize_profile(provider, base_url)
    row.model = model

    _sync_bound_project_presets(db, row)
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
