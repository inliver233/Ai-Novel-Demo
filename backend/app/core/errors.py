from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Avoid zero-arg super() edge cases in production; keep Exception args stable for str(err).
        Exception.__init__(self, self.message)

    @staticmethod
    def unauthorized(message: str = "未登录", *, details: dict[str, Any] | None = None) -> "AppError":
        return AppError(code="UNAUTHORIZED", message=message, status_code=401, details=details or {})

    @staticmethod
    def forbidden(message: str = "无权限", *, details: dict[str, Any] | None = None) -> "AppError":
        return AppError(code="FORBIDDEN", message=message, status_code=403, details=details or {})

    @staticmethod
    def not_found(message: str = "资源不存在", *, details: dict[str, Any] | None = None) -> "AppError":
        return AppError(code="NOT_FOUND", message=message, status_code=404, details=details or {})

    @staticmethod
    def conflict(message: str = "资源冲突", *, details: dict[str, Any] | None = None) -> "AppError":
        return AppError(code="CONFLICT", message=message, status_code=409, details=details or {})

    @staticmethod
    def validation(message: str = "参数错误", *, details: dict[str, Any] | None = None) -> "AppError":
        return AppError(code="VALIDATION_ERROR", message=message, status_code=400, details=details or {})


def error_payload(*, request_id: str, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": request_id,
    }


def ok_payload(*, request_id: str, data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "request_id": request_id}
