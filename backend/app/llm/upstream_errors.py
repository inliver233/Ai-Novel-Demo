from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.errors import AppError


def map_upstream_error(
    status_code: int,
    upstream_text: str | None = None,
    extra_details: dict[str, Any] | None = None,
) -> AppError:
    details: dict[str, Any] = {"status_code": status_code}
    if extra_details:
        details.update(extra_details)
    if upstream_text and settings.app_env == "dev":
        details["upstream_error"] = upstream_text[:500]
    if status_code in (401, 403):
        return AppError(code="LLM_AUTH_ERROR", message="API Key 无效或已过期，请检查后重试", status_code=401, details=details)
    if status_code == 429:
        return AppError(code="LLM_RATE_LIMIT", message="请求过多/额度不足，请稍后重试", status_code=429, details=details)
    if status_code in (400, 422):
        return AppError(code="LLM_BAD_REQUEST", message="请求参数有误，可能是模型名称或参数不支持", status_code=400, details=details)
    if status_code == 408 or status_code == 504:
        return AppError(code="LLM_TIMEOUT", message="请求超时，请稍后重试", status_code=504, details=details)
    return AppError(code="LLM_UPSTREAM_ERROR", message="模型服务异常，请稍后重试", status_code=502, details=details)

