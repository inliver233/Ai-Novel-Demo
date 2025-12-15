from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class OkResponse(BaseModel):
    ok: Literal[True] = True
    data: Any
    request_id: str


class ErrorResponse(BaseModel):
    ok: Literal[False] = False
    error: ErrorInfo
    request_id: str

