from __future__ import annotations

from urllib.parse import urlparse

from app.core.errors import AppError


def normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        raise AppError(code="LLM_CONFIG_ERROR", message="base_url 必须以 http:// 或 https:// 开头", status_code=400)
    if not parsed.netloc:
        raise AppError(code="LLM_CONFIG_ERROR", message="base_url 不合法", status_code=400)
    return normalized


def default_max_tokens_for_provider(provider: str) -> int:
    provider = (provider or "").strip()
    if provider in ("anthropic", "gemini"):
        return 8192
    return 32000
