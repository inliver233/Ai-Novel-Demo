from __future__ import annotations

from app.core.secrets import SecretCryptoError, decrypt_secret
from app.models.project_settings import ProjectSettings


def vector_embedding_overrides(row: ProjectSettings | None) -> dict[str, str | None]:
    """
    Resolve per-project embedding overrides from ProjectSettings.

    Note: this is runtime-only config (may include a decrypted `api_key`).
    Never serialize this dict without passing through `redact_api_keys(...)`.
    """

    if row is None:
        return {}

    out: dict[str, str | None] = {}

    provider = str(getattr(row, "vector_embedding_provider", "") or "").strip()
    if provider:
        out["provider"] = provider

    base_url = str(row.vector_embedding_base_url or "").strip()
    if base_url:
        out["base_url"] = base_url

    model = str(row.vector_embedding_model or "").strip()
    if model:
        out["model"] = model

    azure_deployment = str(getattr(row, "vector_embedding_azure_deployment", "") or "").strip()
    if azure_deployment:
        out["azure_deployment"] = azure_deployment

    azure_api_version = str(getattr(row, "vector_embedding_azure_api_version", "") or "").strip()
    if azure_api_version:
        out["azure_api_version"] = azure_api_version

    st_model = str(getattr(row, "vector_embedding_sentence_transformers_model", "") or "").strip()
    if st_model:
        out["sentence_transformers_model"] = st_model

    if row.vector_embedding_api_key_ciphertext:
        try:
            api_key = decrypt_secret(row.vector_embedding_api_key_ciphertext).strip()
        except SecretCryptoError:
            api_key = ""
        if api_key:
            out["api_key"] = api_key

    return out

