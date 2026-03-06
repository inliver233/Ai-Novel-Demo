from __future__ import annotations

import json
from typing import Any, Iterable, Iterator

from fastapi.responses import StreamingResponse


def format_sse(
    data: dict[str, Any],
    event: str | None = None,
    *,
    event_id: str | int | None = None,
    retry: int | None = None,
) -> str:
    parts: list[str] = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    if event:
        parts.append(f"event: {event}")
    if retry is not None:
        parts.append(f"retry: {int(retry)}")
    parts.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(parts) + "\n\n"


def sse_start(
    *,
    message: str = "????...",
    progress: int = 0,
    status: str = "processing",
) -> str:
    payload: dict[str, Any] = {"type": "start", "message": message, "progress": progress, "status": status}
    return format_sse(payload, event="start")


def sse_progress(
    *,
    message: str,
    progress: int,
    status: str = "processing",
    char_count: int | None = None,
) -> str:
    payload: dict[str, Any] = {"type": "progress", "message": message, "progress": progress, "status": status}
    if char_count is not None:
        payload["char_count"] = char_count
    return format_sse(payload, event="progress")


def sse_chunk(content: str) -> str:
    return format_sse({"type": "chunk", "content": content}, event="token")


def sse_result(data: Any) -> str:
    return format_sse({"type": "result", "data": data}, event="result")


def sse_error(*, error: str, code: int | None = None) -> str:
    payload: dict[str, Any] = {"type": "error", "error": error}
    if code is not None:
        payload["code"] = code
    return format_sse(payload, event="error")


def sse_done() -> str:
    return format_sse({"type": "done"}, event="done")


def sse_heartbeat() -> str:
    return ": heartbeat\n\n"


def create_sse_response(generator: Iterable[str] | Iterator[str]) -> StreamingResponse:
    def wrapper() -> Iterator[str]:
        try:
            yield from generator
        except GeneratorExit:
            close = getattr(generator, "close", None)
            if callable(close):
                close()
            return

    return StreamingResponse(
        wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
