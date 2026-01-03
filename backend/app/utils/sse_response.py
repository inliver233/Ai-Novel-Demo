from __future__ import annotations

import json
from typing import Any, Iterable, Iterator

from fastapi.responses import StreamingResponse


def format_sse(data: dict[str, Any], event: str | None = None) -> str:
    message = ""
    if event:
        message += f"event: {event}\n"
    message += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    return message


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
    return format_sse(payload)


def sse_chunk(content: str) -> str:
    return format_sse({"type": "chunk", "content": content})


def sse_result(data: Any) -> str:
    return format_sse({"type": "result", "data": data})


def sse_error(*, error: str, code: int | None = None) -> str:
    payload: dict[str, Any] = {"type": "error", "error": error}
    if code is not None:
        payload["code"] = code
    return format_sse(payload)


def sse_done() -> str:
    return format_sse({"type": "done"})


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
