from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event
from app.db.utils import new_id
from app.models.chapter import Chapter
from app.models.fractal_memory import FractalMemory
from app.models.story_memory import StoryMemory
from app.services.output_parsers import parse_tag_output
from app.services.prompt_preset_resources import load_preset_resource
from app.services.prompting import render_template

if TYPE_CHECKING:
    from app.services.generation_service import PreparedLlmCall

logger = logging.getLogger("ainovel")

_MAX_DONE_CHAPTERS_PER_REBUILD = 200
_FRACTAL_V2_RESOURCE_KEY = "fractal_v2_v1"
_FRACTAL_V2_TAG = "fractal_v2"

T = TypeVar("T")


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


def _chunks(items: list[T], *, size: int) -> list[list[T]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


@dataclass(frozen=True, slots=True)
class FractalConfig:
    scene_window: int
    arc_window: int
    char_limit: int


def compute_fractal(
    *,
    chapters: list[Chapter],
    config: FractalConfig,
    chapter_summary_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    done = [c for c in chapters if str(c.status or "").strip() == "done"]
    scenes: list[dict[str, Any]] = []
    for c in done:
        summary_override = (chapter_summary_by_id or {}).get(str(c.id)) if chapter_summary_by_id is not None else None
        summary_md = str(summary_override or "").strip() if summary_override is not None else ""
        if not summary_md:
            summary_md = _to_scene_summary(c)
        scenes.append(
            {
                "chapter_id": str(c.id),
                "chapter_number": int(c.number),
                "title": str(c.title or ""),
                "summary_md": summary_md,
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

    v2_cfg = cfg.get("v2") if isinstance(cfg, dict) else None
    v2_summary_md = str(v2_cfg.get("summary_md") or "").strip() if isinstance(v2_cfg, dict) else ""
    v2_text_md = f"<FractalMemoryV2>\n{v2_summary_md}\n</FractalMemoryV2>" if v2_summary_md else ""

    return {
        "enabled": True,
        "disabled_reason": None,
        "config": cfg if isinstance(cfg, dict) else {},
        "v2": v2_cfg if isinstance(v2_cfg, dict) else {},
        "scenes": scenes if isinstance(scenes, list) else [],
        "arcs": arcs if isinstance(arcs, list) else [],
        "sagas": sagas if isinstance(sagas, list) else [],
        "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": text_md},
        "prompt_block_v2": {"identifier": "sys.memory.fractal_v2", "role": "system", "text_md": v2_text_md},
        "updated_at": row.updated_at.isoformat().replace("+00:00", "Z"),
    }


def _render_fractal_v2_prompt(
    *,
    summary_md: str,
    char_limit: int,
    macro_seed: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    resource = load_preset_resource(_FRACTAL_V2_RESOURCE_KEY)
    values: dict[str, Any] = {
        "deterministic_summary_md": summary_md,
        "char_limit": int(char_limit),
    }

    blocks_log: list[dict[str, Any]] = []
    system_parts: list[str] = []
    user_parts: list[str] = []

    for block in resource.blocks:
        if not block.enabled:
            continue
        if block.triggers and _FRACTAL_V2_TAG not in block.triggers:
            continue

        text, missing, error = render_template(block.template, values, macro_seed=macro_seed)
        blocks_log.append(
            {
                "identifier": block.identifier,
                "role": block.role,
                "missing": missing,
                "render_error": error,
                "chars": len(text or ""),
            }
        )
        if not text.strip():
            continue
        role = str(block.role or "").strip().lower()
        if role == "system":
            system_parts.append(text)
        else:
            user_parts.append(text)

    return "\n\n".join(system_parts).strip(), "\n\n".join(user_parts).strip(), blocks_log


def _merge_v2_payload_into_output(*, base_output: dict[str, Any], v2_payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(base_output)
    payload = dict(v2_payload)
    out["v2"] = payload

    summary_md = str(payload.get("summary_md") or "").strip() if bool(payload.get("enabled")) else ""
    text_md = f"<FractalMemoryV2>\n{summary_md}\n</FractalMemoryV2>" if summary_md else ""
    out["prompt_block_v2"] = {
        "identifier": "sys.memory.fractal_v2",
        "role": "system",
        "text_md": text_md,
    }
    return out


def _persist_v2_and_return_context(
    *,
    db: Session,
    row: FractalMemory,
    cfg_dict: dict[str, Any],
    v2_payload: dict[str, Any],
    project_id: str,
    reason: str,
    stage: str,
    base_output: dict[str, Any],
) -> dict[str, Any]:
    next_cfg = dict(cfg_dict)
    next_cfg["v2"] = dict(v2_payload)
    row.config_json = _compact_json_dumps(next_cfg)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        log_event(
            logger,
            "error",
            event="FRACTAL_MEMORY",
            action="rebuild_v2_persist_failed",
            project_id=project_id,
            reason=reason,
            stage=stage,
            disabled_reason=v2_payload.get("disabled_reason"),
            **exception_log_fields(exc),
        )
        return _merge_v2_payload_into_output(base_output=base_output, v2_payload=v2_payload)
    return get_fractal_context(db=db, project_id=project_id, enabled=True)


def rebuild_fractal_memory_v2(
    *,
    db: Session,
    project_id: str,
    reason: str,
    request_id: str,
    actor_user_id: str,
    api_key: str,
    llm_call: PreparedLlmCall | None,
) -> dict[str, Any]:
    """
    LLM rebuild (v2): stores deterministic fractal as baseline and optionally writes a v2 summary.
    Any LLM failure must fallback to deterministic output and record reason in config.v2.
    """
    base = rebuild_fractal_memory(db=db, project_id=project_id, reason=reason)

    row = db.execute(select(FractalMemory).where(FractalMemory.project_id == project_id)).scalars().first()
    if row is None:
        return base

    cfg_obj = _safe_json_loads(row.config_json, default={})
    cfg_dict: dict[str, Any] = cfg_obj if isinstance(cfg_obj, dict) else {}
    base_output = base if isinstance(base, dict) else {}

    sagas = base.get("sagas") if isinstance(base, dict) else None
    latest_summary = ""
    if isinstance(sagas, list) and sagas and isinstance(sagas[-1], dict):
        latest_summary = str(sagas[-1].get("summary_md") or "").strip()

    if not latest_summary:
        v2_payload = {
            "enabled": False,
            "status": "skipped",
            "disabled_reason": "no_content",
        }
        return _persist_v2_and_return_context(
            db=db,
            row=row,
            cfg_dict=cfg_dict,
            v2_payload=v2_payload,
            project_id=project_id,
            reason=reason,
            stage="no_content",
            base_output=base_output,
        )

    if llm_call is None:
        v2_payload = {
            "enabled": False,
            "status": "fallback",
            "disabled_reason": "llm_preset_missing",
        }
        return _persist_v2_and_return_context(
            db=db,
            row=row,
            cfg_dict=cfg_dict,
            v2_payload=v2_payload,
            project_id=project_id,
            reason=reason,
            stage="llm_preset_missing",
            base_output=base_output,
        )

    if not str(api_key or "").strip():
        v2_payload = {
            "enabled": False,
            "status": "fallback",
            "disabled_reason": "api_key_missing",
        }
        return _persist_v2_and_return_context(
            db=db,
            row=row,
            cfg_dict=cfg_dict,
            v2_payload=v2_payload,
            project_id=project_id,
            reason=reason,
            stage="api_key_missing",
            base_output=base_output,
        )

    char_limit = int(cfg_dict.get("char_limit") or 6000)
    system, user, render_blocks = _render_fractal_v2_prompt(summary_md=latest_summary, char_limit=char_limit, macro_seed=request_id)
    render_log = {"task": _FRACTAL_V2_TAG, "resource": _FRACTAL_V2_RESOURCE_KEY, "blocks": render_blocks}
    render_log_json = json.dumps(render_log, ensure_ascii=False)

    from app.services.generation_service import call_llm_and_record, with_param_overrides

    llm_v2_call = with_param_overrides(llm_call, {"temperature": 0.3, "max_tokens": 1024})
    try:
        result = call_llm_and_record(
            logger=logger,
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            chapter_id=None,
            run_type=_FRACTAL_V2_TAG,
            api_key=str(api_key),
            prompt_system=system,
            prompt_user=user,
            prompt_messages=None,
            prompt_render_log_json=render_log_json,
            llm_call=llm_v2_call,
            memory_retrieval_log_json=None,
            run_params_extra_json={
                "fractal_v2": {
                    "char_limit": int(char_limit),
                    "deterministic_summary_chars": len(latest_summary),
                }
            },
        )
    except AppError as exc:
        v2_payload = {
            "enabled": False,
            "status": "fallback",
            "disabled_reason": "llm_error",
            "error_code": exc.code,
        }
        return _persist_v2_and_return_context(
            db=db,
            row=row,
            cfg_dict=cfg_dict,
            v2_payload=v2_payload,
            project_id=project_id,
            reason=reason,
            stage="llm_error",
            base_output=base_output,
        )
    except Exception as exc:
        v2_payload = {
            "enabled": False,
            "status": "fallback",
            "disabled_reason": "internal_error",
            "error_type": type(exc).__name__,
        }
        return _persist_v2_and_return_context(
            db=db,
            row=row,
            cfg_dict=cfg_dict,
            v2_payload=v2_payload,
            project_id=project_id,
            reason=reason,
            stage="internal_error",
            base_output=base_output,
        )

    parsed, warnings, parse_error = parse_tag_output(result.text, tag=_FRACTAL_V2_TAG, output_key="summary_md")
    summary_v2 = str(parsed.get("summary_md") or "").strip()
    if parse_error is not None or not summary_v2:
        v2_payload = {
            "enabled": False,
            "status": "fallback",
            "disabled_reason": "parse_error",
            "run_id": result.run_id,
            "finish_reason": result.finish_reason,
            "warnings": warnings,
            "parse_error": parse_error,
        }
        return _persist_v2_and_return_context(
            db=db,
            row=row,
            cfg_dict=cfg_dict,
            v2_payload=v2_payload,
            project_id=project_id,
            reason=reason,
            stage="parse_error",
            base_output=base_output,
        )

    if char_limit > 0 and len(summary_v2) > char_limit:
        summary_v2 = summary_v2[:char_limit].rstrip() + "…"

    v2_payload = {
        "enabled": True,
        "status": "ok",
        "summary_md": summary_v2,
        "provider": llm_call.provider,
        "model": llm_call.model,
        "run_id": result.run_id,
        "finish_reason": result.finish_reason,
        "latency_ms": int(result.latency_ms),
        "dropped_params": list(result.dropped_params),
        "warnings": warnings,
    }
    out = _persist_v2_and_return_context(
        db=db,
        row=row,
        cfg_dict=cfg_dict,
        v2_payload=v2_payload,
        project_id=project_id,
        reason=reason,
        stage="v2_ok",
        base_output=base_output,
    )

    log_event(
        logger,
        "info",
        event="FRACTAL_MEMORY",
        action="rebuild_v2",
        project_id=project_id,
        reason=reason,
        v2={"enabled": True, "provider": llm_call.provider, "model": llm_call.model},
    )
    return out


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

    done_chapters = [c for c in chapters if str(c.status or "").strip() == "done"]
    done_total = len(done_chapters)

    done_limit = max(1, int(_MAX_DONE_CHAPTERS_PER_REBUILD))
    done_truncated = False
    if done_total > done_limit:
        done_truncated = True
        done_chapters = done_chapters[-done_limit:]

    chapter_summary_by_id: dict[str, str] = {}
    if done_chapters:
        ids = [str(c.id) for c in done_chapters if str(getattr(c, "id", "") or "").strip()]
        if ids:
            rows = (
                db.execute(
                    select(
                        StoryMemory.chapter_id,
                        StoryMemory.content,
                        StoryMemory.updated_at,
                        StoryMemory.created_at,
                        StoryMemory.id,
                    )
                    .where(
                        StoryMemory.project_id == project_id,
                        StoryMemory.memory_type == "chapter_summary",
                        StoryMemory.chapter_id.in_(ids),
                    )
                    .order_by(
                        StoryMemory.chapter_id.asc(),
                        StoryMemory.updated_at.desc(),
                        StoryMemory.created_at.desc(),
                        StoryMemory.id.desc(),
                    )
                )
                .all()
            )
            for chapter_id, content, _updated_at, _created_at, _mem_id in rows:
                cid = str(chapter_id or "").strip()
                if not cid or cid in chapter_summary_by_id:
                    continue
                summary = str(content or "").strip()
                if summary:
                    chapter_summary_by_id[cid] = summary

    computed = compute_fractal(chapters=done_chapters, config=cfg, chapter_summary_by_id=chapter_summary_by_id)
    row = db.execute(select(FractalMemory).where(FractalMemory.project_id == project_id)).scalars().first()
    if row is None:
        row = FractalMemory(id=new_id(), project_id=project_id)
        db.add(row)

    row.config_json = _compact_json_dumps(
        {
            "scene_window": cfg.scene_window,
            "arc_window": cfg.arc_window,
            "char_limit": cfg.char_limit,
            "reason": reason,
            "done_chapters_total": done_total,
            "done_chapters_used": len(done_chapters),
            "done_chapters_limit": done_limit,
            "done_chapters_truncated": bool(done_truncated),
        }
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
