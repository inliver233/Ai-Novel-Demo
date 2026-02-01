from __future__ import annotations

from app.core.config import settings
from app.core.secrets import SecretCryptoError, decrypt_secret
from app.models.project_settings import ProjectSettings


def vector_rerank_overrides(row: ProjectSettings | None) -> dict[str, object]:
    """
    Resolve per-project rerank overrides from ProjectSettings.

    Note: this is runtime-only config (may include a decrypted `api_key`).
    Never serialize this dict without passing through `redact_api_keys(...)`.
    """

    override_enabled = row.vector_rerank_enabled if row is not None else None
    enabled = override_enabled if override_enabled is not None else bool(getattr(settings, "vector_rerank_enabled", False))

    override_method_raw = str(row.vector_rerank_method or "").strip() if row is not None else ""
    method = override_method_raw or "auto"

    override_top_k = row.vector_rerank_top_k if row is not None else None
    top_k = int(override_top_k) if override_top_k is not None else int(getattr(settings, "vector_max_candidates", 20) or 20)
    top_k = max(1, min(int(top_k), 1000))

    override_provider = (getattr(row, "vector_rerank_provider", None) or "").strip() if row is not None else ""
    override_base_url = (getattr(row, "vector_rerank_base_url", None) or "").strip() if row is not None else ""
    override_model = (getattr(row, "vector_rerank_model", None) or "").strip() if row is not None else ""
    override_timeout_seconds = getattr(row, "vector_rerank_timeout_seconds", None) if row is not None else None
    override_hybrid_alpha = getattr(row, "vector_rerank_hybrid_alpha", None) if row is not None else None

    override_api_key_ciphertext = getattr(row, "vector_rerank_api_key_ciphertext", None) if row is not None else None
    override_api_key = ""
    if override_api_key_ciphertext:
        try:
            override_api_key = decrypt_secret(str(override_api_key_ciphertext)).strip()
        except SecretCryptoError:
            override_api_key = ""

    env_base_url = str(getattr(settings, "vector_rerank_external_base_url", "") or "").strip()
    env_model = str(getattr(settings, "vector_rerank_external_model", "") or "").strip()
    env_api_key = str(getattr(settings, "vector_rerank_external_api_key", "") or "").strip()
    env_timeout_raw = float(getattr(settings, "vector_rerank_external_timeout_seconds", 15.0) or 15.0)
    env_timeout_seconds = float(max(1.0, min(env_timeout_raw, 120.0)))

    base_url = override_base_url or env_base_url
    provider = override_provider or ("external_rerank_api" if base_url else "")
    model = override_model or env_model
    timeout_seconds = float(override_timeout_seconds) if override_timeout_seconds is not None else env_timeout_seconds

    hybrid_alpha: float = 0.0
    if override_hybrid_alpha is not None:
        try:
            hybrid_alpha = float(override_hybrid_alpha)
        except Exception:
            hybrid_alpha = 0.0
    hybrid_alpha = max(0.0, min(float(hybrid_alpha), 1.0))

    out: dict[str, object] = {
        "enabled": bool(enabled),
        "method": method,
        "top_k": int(top_k),
        "provider": provider or None,
        "base_url": base_url or None,
        "model": model or None,
        "timeout_seconds": float(timeout_seconds),
        "hybrid_alpha": float(hybrid_alpha),
    }
    api_key_effective = override_api_key or env_api_key
    if api_key_effective:
        out["api_key"] = api_key_effective
    return out

