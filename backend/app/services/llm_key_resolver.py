from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.secrets import SecretCryptoError, decrypt_secret
from app.models.llm_profile import LLMProfile
from app.models.project import Project


def _normalize_header_key(value: str | None) -> str | None:
    key = (value or "").strip()
    return key or None


def normalize_header_api_key(value: str | None) -> str | None:
    return _normalize_header_key(value)


def resolve_api_key_for_project(db: Session, *, project: Project, user_id: str, header_api_key: str | None) -> str:
    header = _normalize_header_key(header_api_key)
    if header is not None:
        return header

    if not project.llm_profile_id:
        raise AppError(code="LLM_KEY_MISSING", message="请先在 Prompts 页保存 API Key", status_code=401)

    profile = db.get(LLMProfile, project.llm_profile_id)
    if profile is None or profile.owner_user_id != user_id:
        raise AppError(code="LLM_KEY_MISSING", message="请先在 Prompts 页保存 API Key", status_code=401)

    return resolve_api_key_for_profile(profile=profile, header_api_key=None)


def resolve_api_key_for_profile(*, profile: LLMProfile, header_api_key: str | None) -> str:
    header = _normalize_header_key(header_api_key)
    if header is not None:
        return header

    if not profile.api_key_ciphertext:
        raise AppError(code="LLM_KEY_MISSING", message="请先在 Prompts 页保存 API Key", status_code=401)

    try:
        resolved = decrypt_secret(profile.api_key_ciphertext).strip()
    except SecretCryptoError:
        raise AppError(
            code="LLM_KEY_MISSING",
            message="已保存的 API Key 无法读取（可能需要迁移或重新保存），请在 Prompts 页重新保存",
            status_code=401,
        )

    if not resolved:
        raise AppError(code="LLM_KEY_MISSING", message="请先在 Prompts 页保存 API Key", status_code=401)

    return resolved


def resolve_api_key(
    db: Session,
    *,
    user_id: str,
    header_api_key: str | None,
    project: Project | None = None,
    profile: LLMProfile | None = None,
) -> str:
    header = _normalize_header_key(header_api_key)
    if header is not None:
        return header

    if profile is not None:
        return resolve_api_key_for_profile(profile=profile, header_api_key=None)

    if project is not None:
        return resolve_api_key_for_project(db, project=project, user_id=user_id, header_api_key=None)

    raise AppError(code="LLM_KEY_MISSING", message="请先在 Prompts 页保存 API Key", status_code=401)
