from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return str(uuid4())


def set_request_id(value: str) -> None:
    request_id_ctx.set(value)


def get_request_id() -> str | None:
    return request_id_ctx.get()

