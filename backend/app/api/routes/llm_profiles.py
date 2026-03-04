from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select, update

from app.api.deps import DbDep, UserIdDep, require_owned_llm_profile
from app.core.errors import AppError, ok_payload
from app.core.secrets import SecretCryptoError, encrypt_secret, mask_api_key
from app.db.utils import new_id
from app.llm.utils import default_max_tokens
from app.models.llm_preset import LLMPreset
from app.models.llm_task_preset import LLMTaskPreset
from app.models.llm_profile import LLMProfile
from app.models.project import Project
from app.schemas.llm_profiles import LLMProfileCreate, LLMProfileOut, LLMProfileUpdate
from app.services.llm_profile_template import (
    DEFAULT_TIMEOUT_SECONDS,
    apply_profile_template_to_llm_row,
    decode_extra_json,
    decode_stop_json,
    encode_extra_json,
    encode_stop_json,
    normalize_base_url_for_provider,
    normalize_max_tokens_for_provider,
)

router = APIRouter()


def _normalize_profile(provider: str, base_url: str | None) -> str | None:
    return normalize_base_url_for_provider(provider, base_url)


def _to_out(row: LLMProfile) -> dict:
    provider = str(row.provider or "").strip()
    model = str(row.model or "").strip()
    return LLMProfileOut(
        id=row.id,
        owner_user_id=row.owner_user_id,
        name=row.name,
        provider=provider,
        base_url=row.base_url,
        model=model,
        temperature=row.temperature,
        top_p=row.top_p,
        max_tokens=normalize_max_tokens_for_provider(provider, model, row.max_tokens),
        presence_penalty=row.presence_penalty,
        frequency_penalty=row.frequency_penalty,
        top_k=row.top_k,
        stop=decode_stop_json(row.stop_json),
        timeout_seconds=int(row.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
        extra=decode_extra_json(row.extra_json),
        has_api_key=bool(row.api_key_ciphertext),
        masked_api_key=row.api_key_masked,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


def _sync_bound_project_presets(db: DbDep, profile: LLMProfile) -> None:
    project_ids = db.execute(select(Project.id).where(Project.llm_profile_id == profile.id)).scalars().all()
    for project_id in project_ids:
        preset = db.get(LLMPreset, project_id)
        if preset is None:
            preset = LLMPreset(
                project_id=project_id,
                provider=profile.provider,
                base_url=_normalize_profile(profile.provider, profile.base_url),
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
        apply_profile_template_to_llm_row(row=preset, profile=profile)

    task_rows = db.execute(select(LLMTaskPreset).where(LLMTaskPreset.llm_profile_id == profile.id)).scalars().all()
    for row in task_rows:
        apply_profile_template_to_llm_row(row=row, profile=profile)


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
    provider = str(body.provider or "").strip()
    model = str(body.model or "").strip()
    row = LLMProfile(
        id=new_id(),
        owner_user_id=user_id,
        name=body.name,
        provider=provider,
        base_url=_normalize_profile(provider, body.base_url),
        model=model,
        temperature=body.temperature,
        top_p=body.top_p,
        max_tokens=normalize_max_tokens_for_provider(provider, model, body.max_tokens),
        presence_penalty=body.presence_penalty,
        frequency_penalty=body.frequency_penalty,
        top_k=body.top_k,
        stop_json=encode_stop_json(body.stop),
        timeout_seconds=int(body.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
        extra_json=encode_extra_json(body.extra),
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

    provider = str(body.provider or row.provider).strip()
    base_url = body.base_url if "base_url" in body.model_fields_set else row.base_url
    model = str(body.model or row.model).strip()

    if body.name is not None:
        row.name = body.name
    if body.provider is not None:
        row.provider = provider
    if "base_url" in body.model_fields_set:
        row.base_url = body.base_url
    if body.model is not None:
        row.model = model

    if "temperature" in body.model_fields_set:
        row.temperature = body.temperature
    if "top_p" in body.model_fields_set:
        row.top_p = body.top_p
    if "max_tokens" in body.model_fields_set:
        row.max_tokens = body.max_tokens
    if "presence_penalty" in body.model_fields_set:
        row.presence_penalty = body.presence_penalty
    if "frequency_penalty" in body.model_fields_set:
        row.frequency_penalty = body.frequency_penalty
    if "top_k" in body.model_fields_set:
        row.top_k = body.top_k
    if "stop" in body.model_fields_set:
        row.stop_json = encode_stop_json(body.stop or [])
    if "timeout_seconds" in body.model_fields_set:
        row.timeout_seconds = int(body.timeout_seconds or DEFAULT_TIMEOUT_SECONDS)
    if "extra" in body.model_fields_set:
        row.extra_json = encode_extra_json(body.extra or {})

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
    row.max_tokens = normalize_max_tokens_for_provider(provider, model, row.max_tokens)
    row.stop_json = encode_stop_json(decode_stop_json(row.stop_json))
    row.timeout_seconds = int(row.timeout_seconds or DEFAULT_TIMEOUT_SECONDS)
    row.extra_json = encode_extra_json(decode_extra_json(row.extra_json))

    _sync_bound_project_presets(db, row)
    db.commit()
    db.refresh(row)
    return ok_payload(request_id=request_id, data={"profile": _to_out(row)})


@router.delete("/llm_profiles/{profile_id}")
def delete_profile(request: Request, db: DbDep, user_id: UserIdDep, profile_id: str) -> dict:
    request_id = request.state.request_id
    row = require_owned_llm_profile(db, profile_id=profile_id, user_id=user_id)

    db.execute(update(Project).where(Project.llm_profile_id == profile_id).values(llm_profile_id=None))
    db.execute(update(LLMTaskPreset).where(LLMTaskPreset.llm_profile_id == profile_id).values(llm_profile_id=None))
    db.delete(row)
    db.commit()
    return ok_payload(request_id=request_id, data={})
