from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.utils import new_id, utc_now
from app.models.generation_run import GenerationRun
from app.models.plot_analysis import PlotAnalysis
from app.models.story_memory import StoryMemory

_MANAGED_MEMORY_TYPES = {"chapter_summary", "hook", "plot_point", "foreshadow", "character_state"}


def _canonical_json(value: dict[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        raise AppError(code="ANALYSIS_PARSE_ERROR", message="analysis 无法序列化为 JSON", status_code=400)


def compute_analysis_hash(analysis: dict[str, Any]) -> tuple[str, str]:
    canonical = _canonical_json(analysis)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical, digest


def validate_analysis_payload(analysis: object) -> dict[str, Any]:
    if not isinstance(analysis, dict):
        raise AppError(code="ANALYSIS_PARSE_ERROR", message="analysis 必须是 JSON object", status_code=400)

    def _ensure_str_field(key: str) -> None:
        if key not in analysis or analysis[key] is None:
            return
        if not isinstance(analysis[key], str):
            raise AppError(code="ANALYSIS_PARSE_ERROR", message=f"analysis.{key} 必须是 string", status_code=400)

    def _ensure_list_of_objects(key: str) -> None:
        if key not in analysis or analysis[key] is None:
            return
        value = analysis[key]
        if not isinstance(value, list):
            raise AppError(code="ANALYSIS_PARSE_ERROR", message=f"analysis.{key} 必须是 list", status_code=400)
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise AppError(
                    code="ANALYSIS_PARSE_ERROR",
                    message=f"analysis.{key}[{idx}] 必须是 object",
                    status_code=400,
                )

    _ensure_str_field("chapter_summary")
    _ensure_str_field("overall_notes")
    _ensure_list_of_objects("hooks")
    _ensure_list_of_objects("plot_points")
    _ensure_list_of_objects("foreshadows")
    _ensure_list_of_objects("character_states")
    _ensure_list_of_objects("suggestions")
    return analysis


def _clamp01(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return float(value)


def _importance_from_item(item: dict[str, Any], default: float) -> float:
    for k in ("importance_score", "importance", "strength"):
        v = item.get(k)
        if isinstance(v, (int, float)):
            num = float(v)
            if k in ("importance", "strength") and num > 1:
                num = num / 10.0
            return _clamp01(num)
    return _clamp01(default)


def _find_position(content_md: str, needle: str) -> tuple[int, int]:
    text = (content_md or "")
    target = (needle or "").strip()
    if not text or not target:
        return -1, 0
    idx = text.find(target)
    if idx < 0:
        return -1, 0
    return int(idx), int(len(target))


def extract_story_memory_seeds(
    *,
    chapter_number: int,
    analysis: dict[str, Any],
    content_md: str,
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    timeline = int(chapter_number)

    chapter_summary = str(analysis.get("chapter_summary") or "").strip()
    if not chapter_summary:
        points = analysis.get("plot_points")
        pieces: list[str] = []
        if isinstance(points, list):
            for item in points:
                if not isinstance(item, dict):
                    continue
                beat = str(item.get("beat") or "").strip()
                excerpt = str(item.get("excerpt") or "").strip()
                if beat:
                    pieces.append(beat)
                elif excerpt:
                    pieces.append(excerpt)
                if len(pieces) >= 3:
                    break
        if pieces:
            chapter_summary = "；".join(pieces).strip()
    if not chapter_summary:
        chapter_summary = (content_md or "").strip()[:300].strip()
    if not chapter_summary:
        chapter_summary = "（未生成摘要）"

    seeds.append(
        {
            "memory_type": "chapter_summary",
            "title": None,
            "content": chapter_summary,
            "full_context_md": None,
            "importance_score": 1.0,
            "tags": ["chapter_summary"],
            "story_timeline": timeline,
            "text_position": -1,
            "text_length": 0,
            "is_foreshadow": 0,
            "foreshadow_resolved_at_chapter_id": None,
            "metadata": None,
        }
    )

    hooks = analysis.get("hooks")
    if isinstance(hooks, list):
        for item in hooks:
            if not isinstance(item, dict):
                continue
            excerpt = str(item.get("excerpt") or "").strip()
            note = str(item.get("note") or "").strip()
            content = note or excerpt
            if not content:
                continue
            pos, length = _find_position(content_md, excerpt)
            seeds.append(
                {
                    "memory_type": "hook",
                    "title": excerpt[:80].strip() or None,
                    "content": content,
                    "full_context_md": None,
                    "importance_score": _importance_from_item(item, 0.7),
                    "tags": ["hook"],
                    "story_timeline": timeline,
                    "text_position": pos,
                    "text_length": length,
                    "is_foreshadow": 0,
                    "foreshadow_resolved_at_chapter_id": None,
                    "metadata": None,
                }
            )

    plot_points = analysis.get("plot_points")
    if isinstance(plot_points, list):
        for item in plot_points:
            if not isinstance(item, dict):
                continue
            beat = str(item.get("beat") or "").strip()
            excerpt = str(item.get("excerpt") or "").strip()
            content = beat or excerpt
            if not content:
                continue
            pos, length = _find_position(content_md, excerpt)
            seeds.append(
                {
                    "memory_type": "plot_point",
                    "title": beat[:80].strip() or None,
                    "content": content,
                    "full_context_md": None,
                    "importance_score": _importance_from_item(item, 0.6),
                    "tags": ["plot_point"],
                    "story_timeline": timeline,
                    "text_position": pos,
                    "text_length": length,
                    "is_foreshadow": 0,
                    "foreshadow_resolved_at_chapter_id": None,
                    "metadata": None,
                }
            )

    foreshadows = analysis.get("foreshadows")
    if isinstance(foreshadows, list):
        for item in foreshadows:
            if not isinstance(item, dict):
                continue
            excerpt = str(item.get("excerpt") or "").strip()
            note = str(item.get("note") or "").strip()
            content = note or excerpt
            if not content:
                continue
            foreshadow_state = 1
            kind = str(item.get("type") or "").strip().lower()
            if kind in {"resolved", "resolve", "resolved_at"}:
                foreshadow_state = 2
            pos, length = _find_position(content_md, excerpt)
            seeds.append(
                {
                    "memory_type": "foreshadow",
                    "title": excerpt[:80].strip() or None,
                    "content": content,
                    "full_context_md": None,
                    "importance_score": _importance_from_item(item, 0.8),
                    "tags": ["foreshadow"],
                    "story_timeline": timeline,
                    "text_position": pos,
                    "text_length": length,
                    "is_foreshadow": foreshadow_state,
                    "foreshadow_resolved_at_chapter_id": None,
                    "metadata": None,
                }
            )

    character_states = analysis.get("character_states")
    if isinstance(character_states, list):
        for item in character_states:
            if not isinstance(item, dict):
                continue
            character_name = str(item.get("character_name") or "").strip()
            state_before = str(item.get("state_before") or "").strip()
            state_after = str(item.get("state_after") or "").strip()
            psychological_change = str(item.get("psychological_change") or "").strip()
            content_parts = [p for p in [state_before, state_after, psychological_change] if p]
            if not content_parts:
                continue
            content = "\n".join(content_parts)
            seeds.append(
                {
                    "memory_type": "character_state",
                    "title": character_name[:80].strip() or None,
                    "content": content,
                    "full_context_md": None,
                    "importance_score": _importance_from_item(item, 0.7),
                    "tags": ["character_state"],
                    "story_timeline": timeline,
                    "text_position": -1,
                    "text_length": 0,
                    "is_foreshadow": 0,
                    "foreshadow_resolved_at_chapter_id": None,
                    "metadata": None,
                }
            )

    return seeds


def apply_chapter_analysis(
    *,
    db: Session,
    request_id: str,
    actor_user_id: str | None,
    project_id: str,
    chapter_id: str,
    chapter_number: int,
    analysis: object,
    draft_content_md: str | None,
) -> dict[str, Any]:
    validated = validate_analysis_payload(analysis)
    canonical_json, analysis_hash = compute_analysis_hash(validated)

    existing = (
        db.execute(select(PlotAnalysis).where(PlotAnalysis.chapter_id == chapter_id).limit(1))
        .scalars()
        .first()
    )

    if existing is not None:
        existing_hash = hashlib.sha256((existing.analysis_json or "").encode("utf-8")).hexdigest()
        if existing_hash == analysis_hash:
            memories = (
                db.execute(
                    select(StoryMemory)
                    .where(StoryMemory.project_id == project_id, StoryMemory.chapter_id == chapter_id)
                    .order_by(StoryMemory.importance_score.desc(), StoryMemory.created_at.asc())
                )
                .scalars()
                .all()
            )
            return {
                "idempotent": True,
                "analysis_hash": analysis_hash,
                "plot_analysis_id": existing.id,
                "memories": [_story_memory_out(m) for m in memories],
            }

    content_md = draft_content_md or ""
    seeds = extract_story_memory_seeds(chapter_number=chapter_number, analysis=validated, content_md=content_md)

    now = utc_now()
    try:
        def _int_or_default(value: object, default: int) -> int:
            if value is None:
                return int(default)
            if isinstance(value, bool):
                return int(default)
            if isinstance(value, int):
                return int(value)
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return int(default)

        if existing is None:
            plot = PlotAnalysis(
                id=new_id(),
                project_id=project_id,
                chapter_id=chapter_id,
                analysis_json=canonical_json,
                created_at=now,
            )
            db.add(plot)
        else:
            existing.analysis_json = canonical_json
            existing.created_at = now
            plot = existing

        db.execute(
            delete(StoryMemory).where(
                StoryMemory.project_id == project_id,
                StoryMemory.chapter_id == chapter_id,
                StoryMemory.memory_type.in_(sorted(_MANAGED_MEMORY_TYPES)),
            )
        )

        created: list[StoryMemory] = []
        for seed in seeds:
            tags = seed.get("tags") or []
            tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
            metadata = seed.get("metadata")
            metadata_json = json.dumps(metadata, ensure_ascii=False) if isinstance(metadata, dict) else None
            created.append(
                StoryMemory(
                    id=new_id(),
                    project_id=project_id,
                    chapter_id=chapter_id,
                    memory_type=str(seed.get("memory_type") or ""),
                    title=seed.get("title"),
                    content=str(seed.get("content") or ""),
                    full_context_md=seed.get("full_context_md"),
                    importance_score=float(seed.get("importance_score") or 0.0),
                    tags_json=tags_json,
                    story_timeline=_int_or_default(seed.get("story_timeline"), chapter_number),
                    text_position=_int_or_default(seed.get("text_position"), -1),
                    text_length=_int_or_default(seed.get("text_length"), 0),
                    is_foreshadow=_int_or_default(seed.get("is_foreshadow"), 0),
                    foreshadow_resolved_at_chapter_id=seed.get("foreshadow_resolved_at_chapter_id"),
                    metadata_json=metadata_json,
                    created_at=now,
                    updated_at=now,
                )
            )

        db.add_all(created)

        if not created:
            raise AppError(code="INTERNAL_ERROR", message="未生成任何 story_memories", status_code=500)

        db.add(
            GenerationRun(
                id=new_id(),
                project_id=project_id,
                actor_user_id=actor_user_id,
                chapter_id=chapter_id,
                type="analysis_apply",
                provider=None,
                model=None,
                request_id=request_id,
                prompt_system=None,
                prompt_user=None,
                prompt_render_log_json=None,
                params_json=json.dumps({"analysis_hash": analysis_hash}, ensure_ascii=False),
                output_text=None,
                error_json=None,
                created_at=now,
            )
        )

        db.commit()
        return {
            "idempotent": False,
            "analysis_hash": analysis_hash,
            "plot_analysis_id": plot.id,
            "memories": [_story_memory_out(m) for m in created],
        }
    except Exception:
        db.rollback()
        raise


def _safe_json(raw: str | None, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _story_memory_out(row: StoryMemory) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "chapter_id": row.chapter_id,
        "memory_type": row.memory_type,
        "title": row.title,
        "content": row.content,
        "importance_score": row.importance_score,
        "tags": _safe_json(row.tags_json, []),
        "story_timeline": row.story_timeline,
        "text_position": row.text_position,
        "text_length": row.text_length,
        "is_foreshadow": row.is_foreshadow,
        "metadata": _safe_json(row.metadata_json, {}),
        "created_at": row.created_at.isoformat(),
    }
