from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import log_event
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.fractal_memory import FractalMemory

logger = logging.getLogger("ainovel")


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_json_loads(value: str | None, *, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _to_scene_summary(chapter: Chapter) -> str:
    summary = str(chapter.summary or "").strip()
    if summary:
        return summary
    content = str(chapter.content_md or "").strip()
    if content:
        s = " ".join(content.split())
        return (s[:280].rstrip() + "…") if len(s) > 280 else s
    plan = str(chapter.plan or "").strip()
    if plan:
        s = " ".join(plan.split())
        return (s[:200].rstrip() + "…") if len(s) > 200 else s
    title = str(chapter.title or "").strip()
    return title or "(empty)"


def _chunks[T](items: list[T], *, size: int) -> list[list[T]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


@dataclass(frozen=True, slots=True)
class FractalConfig:
    scene_window: int
    arc_window: int
    char_limit: int


def compute_fractal(*, chapters: list[Chapter], config: FractalConfig) -> dict[str, Any]:
    done = [c for c in chapters if str(c.status or "").strip() == "done"]
    scenes: list[dict[str, Any]] = []
    for c in done:
        scenes.append(
            {
                "chapter_id": str(c.id),
                "chapter_number": int(c.number),
                "title": str(c.title or ""),
                "summary_md": _to_scene_summary(c),
                "updated_at": c.updated_at.isoformat().replace("+00:00", "Z"),
            }
        )

    arcs: list[dict[str, Any]] = []
    for idx, group in enumerate(_chunks(scenes, size=config.scene_window)):
        lines = [f"- {s['chapter_number']}: {s['summary_md']}" for s in group]
        summary_md = "\n".join(lines).strip()
        if len(summary_md) > 2000:
            summary_md = summary_md[:2000].rstrip() + "…"
        arcs.append(
            {
                "index": idx,
                "scene_chapter_ids": [s["chapter_id"] for s in group],
                "summary_md": summary_md,
            }
        )

    sagas: list[dict[str, Any]] = []
    for idx, group in enumerate(_chunks(arcs, size=config.arc_window)):
        lines = [f"Arc {a['index']}\n{a['summary_md']}".strip() for a in group if a.get("summary_md")]
        summary_md = "\n\n---\n\n".join(lines).strip()
        if len(summary_md) > 4000:
            summary_md = summary_md[:4000].rstrip() + "…"
        sagas.append(
            {
                "index": idx,
                "arc_indices": [a["index"] for a in group],
                "summary_md": summary_md,
            }
        )

    latest_saga = sagas[-1]["summary_md"] if sagas else ""
    text_md = ""
    if latest_saga.strip():
        body = latest_saga.strip()
        if config.char_limit >= 0 and len(body) > config.char_limit:
            body = body[: config.char_limit].rstrip() + "…"
        text_md = f"<FractalMemory>\n{body}\n</FractalMemory>"

    return {
        "scenes": scenes,
        "arcs": arcs,
        "sagas": sagas,
        "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": text_md},
    }


def get_fractal_context(*, db: Session, project_id: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "disabled_reason": "disabled",
            "config": {},
            "scenes": [],
            "arcs": [],
            "sagas": [],
            "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": ""},
        }

    row = db.execute(select(FractalMemory).where(FractalMemory.project_id == project_id)).scalars().first()
    if row is None:
        return {
            "enabled": False,
            "disabled_reason": "not_built",
            "config": {},
            "scenes": [],
            "arcs": [],
            "sagas": [],
            "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": ""},
        }

    cfg = _safe_json_loads(row.config_json, default={})
    scenes = _safe_json_loads(row.scenes_json, default=[])
    arcs = _safe_json_loads(row.arcs_json, default=[])
    sagas = _safe_json_loads(row.sagas_json, default=[])
    latest = sagas[-1]["summary_md"] if isinstance(sagas, list) and sagas and isinstance(sagas[-1], dict) else ""
    text_md = f"<FractalMemory>\n{latest.strip()}\n</FractalMemory>" if isinstance(latest, str) and latest.strip() else ""

    return {
        "enabled": True,
        "disabled_reason": None,
        "config": cfg if isinstance(cfg, dict) else {},
        "scenes": scenes if isinstance(scenes, list) else [],
        "arcs": arcs if isinstance(arcs, list) else [],
        "sagas": sagas if isinstance(sagas, list) else [],
        "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": text_md},
        "updated_at": row.updated_at.isoformat().replace("+00:00", "Z"),
    }


def rebuild_fractal_memory(*, db: Session, project_id: str, reason: str) -> dict[str, Any]:
    """
    Deterministic rebuild: same chapters -> same output (idempotent on content).
    """
    t0 = time.perf_counter()

    cfg = FractalConfig(
        scene_window=max(1, int(getattr(settings, "fractal_scene_window", 5) or 5)),
        arc_window=max(1, int(getattr(settings, "fractal_arc_window", 5) or 5)),
        char_limit=max(0, int(getattr(settings, "fractal_char_limit", 6000) or 6000)),
    )

    chapters = (
        db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.number.asc()))
        .scalars()
        .all()
    )

    computed = compute_fractal(chapters=chapters, config=cfg)
    row = db.execute(select(FractalMemory).where(FractalMemory.project_id == project_id)).scalars().first()
    if row is None:
        row = FractalMemory(id=new_id(), project_id=project_id)
        db.add(row)

    row.config_json = _compact_json_dumps(
        {"scene_window": cfg.scene_window, "arc_window": cfg.arc_window, "char_limit": cfg.char_limit, "reason": reason}
    )
    row.scenes_json = _compact_json_dumps(computed["scenes"])
    row.arcs_json = _compact_json_dumps(computed["arcs"])
    row.sagas_json = _compact_json_dumps(computed["sagas"])

    db.commit()
    out = get_fractal_context(db=db, project_id=project_id, enabled=True)

    log_event(
        logger,
        "info",
        event="FRACTAL_MEMORY",
        action="rebuild",
        project_id=project_id,
        reason=reason,
        counts={"scenes": len(out.get("scenes") or []), "arcs": len(out.get("arcs") or []), "sagas": len(out.get("sagas") or [])},
        timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
    )
    return out

