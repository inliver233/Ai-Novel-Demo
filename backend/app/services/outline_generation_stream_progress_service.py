from __future__ import annotations

import time
from collections.abc import Callable, Generator
from dataclasses import dataclass

from app.utils.sse_response import sse_chunk, sse_heartbeat, sse_progress, sse_result

ProgressMessageBuilder = Callable[[dict[str, object] | None], str]


@dataclass(slots=True)
class _SegmentProgressState:
    last_ping: float = 0.0
    last_message: str = ""
    last_snapshot_key: tuple[str, int, int, int] | None = None
    last_raw_preview_key: tuple[str, int, int, int] | None = None


@dataclass(slots=True)
class _FillProgressState:
    last_ping: float = 0.0
    last_message: str = ""
    last_snapshot_marker: tuple[str, int] | None = None


def iter_segment_progress_sse_events(
    *,
    future,
    progress_events: list[dict[str, object]],
    progress_lock,
    heartbeat_interval: float,
    poll_interval: float,
    progress_message_builder: ProgressMessageBuilder,
) -> Generator[str, None, None]:
    state = _SegmentProgressState()
    while True:
        now = time.monotonic()
        if now - state.last_ping >= heartbeat_interval:
            yield sse_heartbeat()
            state.last_ping = now
        with progress_lock:
            pending_snapshots = list(progress_events)
            progress_events.clear()
        for snapshot in pending_snapshots:
            yield from _map_segment_snapshot(snapshot=snapshot, state=state, progress_message_builder=progress_message_builder)
        if future.done():
            break
        time.sleep(poll_interval)


def iter_fill_progress_sse_events(
    *,
    future,
    progress_events: list[dict[str, object]],
    progress_lock,
    heartbeat_interval: float,
    poll_interval: float,
    progress_message_builder: ProgressMessageBuilder,
    preview_outline_md: str,
) -> Generator[str, None, None]:
    state = _FillProgressState()
    while True:
        now = time.monotonic()
        if now - state.last_ping >= heartbeat_interval:
            yield sse_heartbeat()
            state.last_ping = now
        with progress_lock:
            pending_snapshots = list(progress_events)
            progress_events.clear()
        for snapshot in pending_snapshots:
            yield from _map_fill_snapshot(
                snapshot=snapshot,
                state=state,
                progress_message_builder=progress_message_builder,
                preview_outline_md=preview_outline_md,
            )
        if future.done():
            break
        time.sleep(poll_interval)


def _map_segment_snapshot(
    *,
    snapshot: dict[str, object],
    state: _SegmentProgressState,
    progress_message_builder: ProgressMessageBuilder,
) -> Generator[str, None, None]:
    event_name = str(snapshot.get("event") or "")
    batch_idx = int(snapshot.get("batch_index") or 0)
    attempt = int(snapshot.get("attempt") or 0)
    completed_count = int(snapshot.get("completed_count") or 0)
    snapshot_chapters = snapshot.get("chapters_snapshot")
    snapshot_outline_md = str(snapshot.get("outline_md") or "")
    if event_name in (
        "batch_applied",
        "fill_attempt_applied",
        "fill_gap_repair_applied",
        "fill_gap_repair_final_sweep_applied",
    ) and isinstance(snapshot_chapters, list):
        snapshot_key = (event_name, batch_idx, attempt, completed_count)
        if snapshot_key != state.last_snapshot_key:
            yield sse_result({"outline_md": snapshot_outline_md, "chapters": snapshot_chapters})
            state.last_snapshot_key = snapshot_key

    raw_preview = str(snapshot.get("raw_output_preview") or "").strip()
    raw_chars_raw = snapshot.get("raw_output_chars")
    try:
        raw_chars = int(raw_chars_raw) if raw_chars_raw is not None else len(raw_preview)
    except Exception:
        raw_chars = len(raw_preview)
    if raw_preview:
        raw_key = (event_name, batch_idx, attempt, raw_chars)
        if raw_key != state.last_raw_preview_key:
            yield sse_chunk(_build_segment_raw_preview_chunk(snapshot=snapshot, event_name=event_name, batch_idx=batch_idx, attempt=attempt, raw_preview=raw_preview))
            state.last_raw_preview_key = raw_key

    progress_percent = snapshot.get("progress_percent")
    if isinstance(progress_percent, int):
        progress_num = max(10, min(98, progress_percent))
    else:
        progress_num = 10
    message = progress_message_builder(snapshot)
    if message != state.last_message:
        yield sse_progress(message=message, progress=progress_num)
        state.last_message = message


def _map_fill_snapshot(
    *,
    snapshot: dict[str, object],
    state: _FillProgressState,
    progress_message_builder: ProgressMessageBuilder,
    preview_outline_md: str,
) -> Generator[str, None, None]:
    snapshot_event = str(snapshot.get("event") or "")
    snapshot_attempt_raw = snapshot.get("attempt")
    if isinstance(snapshot_attempt_raw, int):
        snapshot_attempt = snapshot_attempt_raw
    else:
        try:
            snapshot_attempt = int(snapshot_attempt_raw) if snapshot_attempt_raw is not None else 0
        except Exception:
            snapshot_attempt = 0
    snapshot_chapters = snapshot.get("chapters_snapshot")
    snapshot_marker = (snapshot_event, snapshot_attempt)
    if (
        snapshot_event in ("attempt_applied", "gap_repair_applied", "gap_repair_final_sweep_applied")
        and snapshot_marker != state.last_snapshot_marker
        and isinstance(snapshot_chapters, list)
    ):
        yield sse_result({"outline_md": preview_outline_md, "chapters": snapshot_chapters})
        state.last_snapshot_marker = snapshot_marker

    message = progress_message_builder(snapshot)
    if message != state.last_message:
        yield sse_progress(message=message, progress=94)
        state.last_message = message


def _build_segment_raw_preview_chunk(
    *,
    snapshot: dict[str, object],
    event_name: str,
    batch_idx: int,
    attempt: int,
    raw_preview: str,
) -> str:
    batch_count_raw = snapshot.get("batch_count")
    try:
        batch_count = int(batch_count_raw) if batch_count_raw is not None else 0
    except Exception:
        batch_count = 0

    title_parts = [event_name or "segment"]
    if batch_idx > 0 and batch_count > 0:
        title_parts.append(f"batch {batch_idx}/{batch_count}")
    elif batch_idx > 0:
        title_parts.append(f"batch {batch_idx}")
    if attempt > 0:
        title_parts.append(f"attempt {attempt}")
    title = " | ".join(title_parts)
    return f"\n\n[{title}]\n{raw_preview}\n"
