from __future__ import annotations

import json

from fastapi import APIRouter, Request

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.core.config import settings
from app.core.errors import AppError, ok_payload
from app.core.secrets import SecretCryptoError, decrypt_secret, encrypt_secret, mask_api_key
from app.models.project_settings import ProjectSettings
from app.schemas.settings import ProjectSettingsOut, ProjectSettingsUpdate, QueryPreprocessingConfig

router = APIRouter()

_VECTOR_DISABLED_BASE_URL_MISSING = "embedding_base_url_missing"
_VECTOR_DISABLED_MODEL_MISSING = "embedding_model_missing"
_VECTOR_DISABLED_API_KEY_MISSING = "embedding_api_key_missing"
_VECTOR_DISABLED_API_KEY_DECRYPT_FAILED = "embedding_api_key_decrypt_failed"


def _parse_query_preprocessing_json(raw: str | None) -> QueryPreprocessingConfig | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        return QueryPreprocessingConfig.model_validate(data)
    except ValueError:
        return None


def _vector_effective_disabled_reason(*, base_url: str, model: str, has_api_key: bool) -> str | None:
    if not base_url.strip():
        return _VECTOR_DISABLED_BASE_URL_MISSING
    if not model.strip():
        return _VECTOR_DISABLED_MODEL_MISSING
    if not has_api_key:
        return _VECTOR_DISABLED_API_KEY_MISSING
    return None


def _build_settings_payload(*, project_id: str, row: ProjectSettings | None) -> dict:
    world_setting = (row.world_setting or "") if row is not None else ""
    style_guide = (row.style_guide or "") if row is not None else ""
    constraints = (row.constraints or "") if row is not None else ""

    qp_default = QueryPreprocessingConfig()
    qp_override = _parse_query_preprocessing_json((row.query_preprocessing_json or "").strip() if row is not None else None)
    qp_effective = qp_override or qp_default
    qp_source = "project" if qp_override is not None else "default"

    rerank_override_enabled = row.vector_rerank_enabled if row is not None else None
    rerank_override_method_raw = (row.vector_rerank_method or "").strip() if row is not None else ""
    rerank_override_method = rerank_override_method_raw or None
    rerank_override_top_k = row.vector_rerank_top_k if row is not None else None

    rerank_default_enabled = bool(getattr(settings, "vector_rerank_enabled", False))
    rerank_default_method = "auto"
    rerank_default_top_k = int(getattr(settings, "vector_max_candidates", 20) or 20)

    rerank_effective_enabled = rerank_override_enabled if rerank_override_enabled is not None else rerank_default_enabled
    rerank_effective_method = rerank_override_method or rerank_default_method
    rerank_effective_top_k = rerank_override_top_k if rerank_override_top_k is not None else rerank_default_top_k

    source_project_fields = {
        "enabled": rerank_override_enabled is not None,
        "method": rerank_override_method is not None,
        "top_k": rerank_override_top_k is not None,
    }
    source_default_fields = {
        "enabled": rerank_override_enabled is None,
        "method": rerank_override_method is None,
        "top_k": rerank_override_top_k is None,
    }
    if any(source_project_fields.values()) and any(source_default_fields.values()):
        rerank_effective_source = "mixed"
    elif any(source_project_fields.values()):
        rerank_effective_source = "project"
    else:
        rerank_effective_source = "default"

    override_base_url = (row.vector_embedding_base_url or "").strip() if row is not None else ""
    override_model = (row.vector_embedding_model or "").strip() if row is not None else ""
    override_ciphertext = row.vector_embedding_api_key_ciphertext if row is not None else None
    override_masked = (row.vector_embedding_api_key_masked or "").strip() if row is not None else ""
    override_has_api_key = bool(override_ciphertext)

    env_base_url = str(settings.vector_embedding_base_url or "").strip()
    env_model = str(settings.vector_embedding_model or "").strip()
    env_api_key = str(settings.vector_embedding_api_key or "").strip()
    env_has_api_key = bool(env_api_key)
    env_masked = mask_api_key(env_api_key) if env_api_key else ""

    override_api_key_ok = False
    if override_ciphertext:
        try:
            _ = decrypt_secret(override_ciphertext)
            override_api_key_ok = True
        except SecretCryptoError:
            override_api_key_ok = False

    effective_base_url = override_base_url or env_base_url
    effective_model = override_model or env_model
    effective_has_api_key = override_api_key_ok or env_has_api_key
    effective_masked = override_masked if override_api_key_ok else env_masked

    source_project_fields = {
        "base_url": bool(override_base_url),
        "model": bool(override_model),
        "api_key": bool(override_api_key_ok),
    }
    source_env_fields = {
        "base_url": (not override_base_url) and bool(env_base_url),
        "model": (not override_model) and bool(env_model),
        "api_key": (not override_api_key_ok) and bool(env_has_api_key),
    }
    if any(source_project_fields.values()) and any(source_env_fields.values()):
        effective_source = "mixed"
    elif any(source_project_fields.values()):
        effective_source = "project"
    elif any(source_env_fields.values()):
        effective_source = "env"
    else:
        effective_source = "none"

    disabled_reason = _vector_effective_disabled_reason(
        base_url=effective_base_url,
        model=effective_model,
        has_api_key=effective_has_api_key,
    )
    if disabled_reason is None and override_has_api_key and not override_api_key_ok and not env_has_api_key:
        disabled_reason = _VECTOR_DISABLED_API_KEY_DECRYPT_FAILED

    payload = ProjectSettingsOut(
        project_id=project_id,
        world_setting=world_setting,
        style_guide=style_guide,
        constraints=constraints,
        query_preprocessing=qp_override,
        query_preprocessing_default=qp_default,
        query_preprocessing_effective=qp_effective,
        query_preprocessing_effective_source=qp_source,
        vector_rerank_enabled=rerank_override_enabled,
        vector_rerank_method=rerank_override_method,
        vector_rerank_top_k=rerank_override_top_k,
        vector_rerank_effective_enabled=rerank_effective_enabled,
        vector_rerank_effective_method=rerank_effective_method,
        vector_rerank_effective_top_k=rerank_effective_top_k,
        vector_rerank_effective_source=rerank_effective_source,
        vector_embedding_base_url=override_base_url,
        vector_embedding_model=override_model,
        vector_embedding_has_api_key=override_has_api_key,
        vector_embedding_masked_api_key=override_masked,
        vector_embedding_effective_base_url=effective_base_url,
        vector_embedding_effective_model=effective_model,
        vector_embedding_effective_has_api_key=effective_has_api_key,
        vector_embedding_effective_masked_api_key=effective_masked,
        vector_embedding_effective_disabled_reason=disabled_reason,
        vector_embedding_effective_source=effective_source,
    ).model_dump()
    return payload


@router.get("/projects/{project_id}/settings")
def get_settings(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    row = db.get(ProjectSettings, project_id)
    payload = _build_settings_payload(project_id=project_id, row=row)
    return ok_payload(request_id=request_id, data={"settings": payload})


@router.put("/projects/{project_id}/settings")
def put_settings(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: ProjectSettingsUpdate) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id, world_setting="", style_guide="", constraints="")
        db.add(row)

    if body.world_setting is not None:
        row.world_setting = body.world_setting
    if body.style_guide is not None:
        row.style_guide = body.style_guide
    if body.constraints is not None:
        row.constraints = body.constraints

    if "query_preprocessing" in body.model_fields_set:
        if body.query_preprocessing is None:
            row.query_preprocessing_json = None
        else:
            row.query_preprocessing_json = json.dumps(
                body.query_preprocessing.model_dump(),
                ensure_ascii=False,
                separators=(",", ":"),
            )

    if "vector_rerank_enabled" in body.model_fields_set:
        row.vector_rerank_enabled = body.vector_rerank_enabled

    if "vector_rerank_method" in body.model_fields_set:
        if body.vector_rerank_method is None:
            row.vector_rerank_method = None
        else:
            row.vector_rerank_method = body.vector_rerank_method.strip() or None

    if "vector_rerank_top_k" in body.model_fields_set:
        row.vector_rerank_top_k = int(body.vector_rerank_top_k) if body.vector_rerank_top_k is not None else None

    if body.vector_embedding_base_url is not None:
        row.vector_embedding_base_url = body.vector_embedding_base_url.strip() or None
    if body.vector_embedding_model is not None:
        row.vector_embedding_model = body.vector_embedding_model.strip() or None
    if body.vector_embedding_api_key is not None:
        raw = body.vector_embedding_api_key.strip()
        if not raw:
            row.vector_embedding_api_key_ciphertext = None
            row.vector_embedding_api_key_masked = None
        else:
            try:
                row.vector_embedding_api_key_ciphertext = encrypt_secret(raw)
                row.vector_embedding_api_key_masked = mask_api_key(raw)
            except SecretCryptoError as exc:
                raise AppError.validation(
                    message=str(exc),
                    details={"field": "vector_embedding_api_key"},
                ) from exc

    db.commit()
    db.refresh(row)
    payload = _build_settings_payload(project_id=project_id, row=row)
    return ok_payload(request_id=request_id, data={"settings": payload})
