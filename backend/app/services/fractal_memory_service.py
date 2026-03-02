from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
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
from app.services.context_budget_observability import build_budget_observability
from app.services.output_parsers import parse_tag_output
from app.services.prompt_preset_resources import load_preset_resource
from app.services.prompting import render_template

if TYPE_CHECKING:
    from app.services.generation_service import PreparedLlmCall

logger = logging.getLogger("ainovel")

_DEFAULT_MAX_DONE_CHAPTERS_PER_REBUILD = 1000
_FRACTAL_V2_RESOURCE_KEY = "fractal_v2_v1"
_FRACTAL_V2_TAG = "fractal_v2"
_TOKEN_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]{2,}")
_FRACTAL_DROPPED_REASON_EXPLAIN = {
    "recent_window_budget": "最近窗口只保留最近 N 章高频记忆。",
    "prompt_char_budget": "Fractal 注入文本超过字符预算后被截断。",
    "done_chapters_budget": "重建时 done 章节超过可处理上限，仅使用最近窗口。",
    "long_retrieval_budget": "长期索引命中数量超过 max_hits，仅保留前 N 条。",
}

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
    recent_window_chapters: int
    mid_window_chapters: int
    long_window_chapters: int
    long_index_terms: int
    long_retrieval_hits: int


def _clip_text(text: str, *, limit: int) -> str:
    body = str(text or "").strip()
    if limit <= 0:
        return body
    if len(body) <= limit:
        return body
    return body[:limit].rstrip() + "…"


def _extract_keywords(text: str, *, limit: int) -> list[str]:
    if limit <= 0:
        return []
    counts: Counter[str] = Counter()
    for raw in _TOKEN_RE.findall(str(text or "")):
        token = str(raw or "").strip().lower()
        if len(token) < 2:
            continue
        counts[token] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:limit]]


def _sample_scene_lines(*, scenes: list[dict[str, Any]], max_items: int) -> list[str]:
    if not scenes:
        return []
    if max_items <= 0 or len(scenes) <= max_items:
        picked = scenes
    else:
        head = min(3, max_items)
        tail = min(2, max(0, max_items - head))
        mid = max(0, max_items - head - tail)
        chunks: list[list[dict[str, Any]]] = [scenes[:head]]
        if mid > 0:
            start = max(0, (len(scenes) // 2) - (mid // 2))
            chunks.append(scenes[start : start + mid])
        if tail > 0:
            chunks.append(scenes[-tail:])
        picked = []
        seen_ids: set[str] = set()
        for group in chunks:
            for row in group:
                key = str(row.get("chapter_id") or "")
                if key and key in seen_ids:
                    continue
                if key:
                    seen_ids.add(key)
                picked.append(row)
    lines: list[str] = []
    for row in picked:
        chapter_number = int(row.get("chapter_number") or 0)
        title = str(row.get("title") or "").strip()
        summary_md = str(row.get("summary_md") or "").strip()
        if not summary_md:
            continue
        prefix = f"第{chapter_number}章"
        if title:
            prefix += f" {title}"
        lines.append(f"- {prefix}: {summary_md}")
    return lines


def _build_fractal_prompt_inner(
    *,
    recent_chapters: list[dict[str, Any]],
    latest_mid_stage: dict[str, Any] | None,
    latest_long_outline: dict[str, Any] | None,
    long_hits: list[dict[str, Any]] | None,
) -> str:
    sections: list[str] = []

    recent_lines = _sample_scene_lines(scenes=recent_chapters, max_items=10)
    if recent_lines:
        sections.append("## 最近窗口（高频）\n" + "\n".join(recent_lines))

    if isinstance(latest_mid_stage, dict):
        start = int(latest_mid_stage.get("range_start_chapter") or 0)
        end = int(latest_mid_stage.get("range_end_chapter") or 0)
        summary_md = str(latest_mid_stage.get("summary_md") or "").strip()
        if summary_md:
            sections.append(f"## 中期摘要（阶段 {start}-{end}）\n{summary_md}")

    if isinstance(latest_long_outline, dict):
        start = int(latest_long_outline.get("range_start_chapter") or 0)
        end = int(latest_long_outline.get("range_end_chapter") or 0)
        summary_md = str(latest_long_outline.get("summary_md") or "").strip()
        keywords = latest_long_outline.get("keywords") if isinstance(latest_long_outline.get("keywords"), list) else []
        if summary_md:
            block = [f"## 长期总纲（低频压缩 {start}-{end}）", summary_md]
            if keywords:
                block.append("索引关键词: " + ", ".join(str(k) for k in keywords[:12] if str(k or "").strip()))
            sections.append("\n".join(block))

    hit_rows = long_hits or []
    if hit_rows:
        hit_lines: list[str] = []
        for hit in hit_rows:
            start = int(hit.get("range_start_chapter") or 0)
            end = int(hit.get("range_end_chapter") or 0)
            reason = str(hit.get("reason") or "matched")
            summary_md = _clip_text(str(hit.get("summary_md") or ""), limit=280)
            hit_lines.append(f"- [{reason}] {start}-{end}: {summary_md}")
        if hit_lines:
            sections.append("## 长期索引命中\n" + "\n".join(hit_lines))

    return "\n\n".join(s for s in sections if str(s).strip()).strip()


def _fractal_budget_observability(
    *,
    config: FractalConfig,
    dropped: list[dict[str, Any]],
    done_limit: int | None = None,
) -> dict[str, Any]:
    limits = {
        "scene_window": int(config.scene_window),
        "arc_window": int(config.arc_window),
        "char_limit": int(config.char_limit),
        "recent_window_chapters": int(config.recent_window_chapters),
        "mid_window_chapters": int(config.mid_window_chapters),
        "long_window_chapters": int(config.long_window_chapters),
        "long_index_terms": int(config.long_index_terms),
    }
    if done_limit is not None:
        limits["done_chapters_per_rebuild"] = int(done_limit)
    return build_budget_observability(
        module="fractal",
        limits=limits,
        dropped=dropped,
        reason_explain=_FRACTAL_DROPPED_REASON_EXPLAIN,
    )


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

    recent_window = max(1, int(config.recent_window_chapters))
    recent_window_chapters = scenes[-recent_window:] if scenes else []

    mid_window = max(1, int(config.mid_window_chapters))
    mid_stages: list[dict[str, Any]] = []
    for idx, group in enumerate(_chunks(scenes, size=mid_window)):
        if not group:
            continue
        stage_lines = _sample_scene_lines(scenes=group, max_items=8)
        summary_md = _clip_text("\n".join(stage_lines), limit=2600)
        mid_stages.append(
            {
                "index": idx,
                "chapter_ids": [str(item.get("chapter_id") or "") for item in group if str(item.get("chapter_id") or "").strip()],
                "range_start_chapter": int(group[0].get("chapter_number") or 0),
                "range_end_chapter": int(group[-1].get("chapter_number") or 0),
                "summary_md": summary_md,
            }
        )

    long_window = max(1, int(config.long_window_chapters))
    stages_per_long = max(1, long_window // mid_window)
    long_outlines: list[dict[str, Any]] = []
    for idx, group in enumerate(_chunks(mid_stages, size=stages_per_long)):
        if not group:
            continue
        summary_lines: list[str] = []
        for stage in group:
            start = int(stage.get("range_start_chapter") or 0)
            end = int(stage.get("range_end_chapter") or 0)
            stage_summary = _clip_text(str(stage.get("summary_md") or ""), limit=260)
            summary_lines.append(f"- 阶段 {start}-{end}: {stage_summary}")
        summary_md = _clip_text("\n".join(summary_lines), limit=3200)
        keywords = _extract_keywords(summary_md, limit=max(1, int(config.long_index_terms)))
        long_outlines.append(
            {
                "index": idx,
                "stage_indices": [int(stage.get("index") or 0) for stage in group],
                "range_start_chapter": int(group[0].get("range_start_chapter") or 0),
                "range_end_chapter": int(group[-1].get("range_end_chapter") or 0),
                "summary_md": summary_md,
                "keywords": keywords,
            }
        )

    long_index = [
        {
            "outline_index": int(item.get("index") or 0),
            "range_start_chapter": int(item.get("range_start_chapter") or 0),
            "range_end_chapter": int(item.get("range_end_chapter") or 0),
            "keywords": list(item.get("keywords") or []),
        }
        for item in long_outlines
        if isinstance(item, dict)
    ]

    layers = {
        "recent_window": {
            "window_chapters": int(recent_window),
            "total_done": len(scenes),
            "used": len(recent_window_chapters),
            "chapters": recent_window_chapters,
        },
        "mid_term": {
            "window_chapters": int(mid_window),
            "stages": mid_stages,
        },
        "long_term": {
            "window_chapters": int(long_window),
            "outlines": long_outlines,
            "retrievable_index": long_index,
        },
    }

    prompt_inner = _build_fractal_prompt_inner(
        recent_chapters=recent_window_chapters,
        latest_mid_stage=mid_stages[-1] if mid_stages else None,
        latest_long_outline=long_outlines[-1] if long_outlines else None,
        long_hits=None,
    )
    if not prompt_inner:
        latest_saga = sagas[-1]["summary_md"] if sagas else ""
        prompt_inner = str(latest_saga or "").strip()
    prompt_original_chars = len(prompt_inner)
    prompt_inner = _clip_text(prompt_inner, limit=max(0, int(config.char_limit)))
    prompt_truncated = bool(max(0, int(config.char_limit)) > 0 and prompt_original_chars > int(config.char_limit))
    text_md = f"<FractalMemory>\n{prompt_inner}\n</FractalMemory>" if prompt_inner else ""

    dropped: list[dict[str, Any]] = []
    if len(scenes) > len(recent_window_chapters):
        dropped.append({"reason": "recent_window_budget", "count": len(scenes) - len(recent_window_chapters)})
    if prompt_truncated:
        dropped.append({"reason": "prompt_char_budget", "count": 1})
    budget_obs = _fractal_budget_observability(config=config, dropped=dropped)

    return {
        "scenes": scenes,
        "arcs": arcs,
        "sagas": sagas,
        "layers": layers,
        "dropped": dropped,
        "budget_observability": budget_obs,
        "prompt_block": {
            "identifier": "sys.memory.fractal",
            "role": "system",
            "text_md": text_md,
            "truncated": bool(prompt_truncated),
            "char_limit": int(config.char_limit),
            "original_chars": int(prompt_original_chars),
        },
    }


def _query_tokens(query_text: str, *, limit: int = 24) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_RE.findall(str(query_text or "")):
        token = str(raw or "").strip().lower()
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            break
    return out


def select_fractal_long_term_hits(
    *,
    layers: dict[str, Any],
    query_text: str,
    max_hits: int,
) -> dict[str, Any]:
    long_term = layers.get("long_term") if isinstance(layers, dict) else None
    outlines = long_term.get("outlines") if isinstance(long_term, dict) else None
    tokens = _query_tokens(query_text)
    if not tokens or not isinstance(outlines, list) or max_hits <= 0:
        return {
            "query_text": str(query_text or ""),
            "tokens": tokens,
            "total_candidates": 0,
            "hit_count": 0,
            "max_hits": int(max_hits),
            "hits": [],
            "dropped": [],
        }

    token_set = set(tokens)
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for row in outlines:
        if not isinstance(row, dict):
            continue
        keywords_raw = row.get("keywords")
        keywords = [str(k or "").strip().lower() for k in (keywords_raw if isinstance(keywords_raw, list) else []) if str(k or "").strip()]
        keyword_set = set(keywords)
        keyword_hits = sorted(token_set & keyword_set)
        summary_md = str(row.get("summary_md") or "").strip()
        summary_lower = summary_md.lower()
        summary_hits = sorted({t for t in token_set if t and t in summary_lower})
        if not keyword_hits and not summary_hits:
            continue
        score = (len(keyword_hits) * 3) + len(summary_hits)
        scored.append(
            (
                score,
                int(row.get("index") or 0),
                {
                    "outline_index": int(row.get("index") or 0),
                    "range_start_chapter": int(row.get("range_start_chapter") or 0),
                    "range_end_chapter": int(row.get("range_end_chapter") or 0),
                    "keywords": keywords,
                    "matched_keywords": keyword_hits,
                    "matched_tokens": summary_hits,
                    "reason": "keyword_match" if keyword_hits else "summary_match",
                    "score": int(score),
                    "summary_md": summary_md,
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]))
    limit = max(0, int(max_hits))
    hits = [entry for _score, _index, entry in scored[:limit]]
    dropped: list[dict[str, Any]] = []
    if len(scored) > len(hits):
        dropped.append({"reason": "long_retrieval_budget", "count": len(scored) - len(hits)})
    return {
        "query_text": str(query_text or ""),
        "tokens": tokens,
        "total_candidates": int(len(scored)),
        "hit_count": len(hits),
        "max_hits": int(limit),
        "hits": hits,
        "dropped": dropped,
    }


def enrich_fractal_context_for_query(
    *,
    fractal_context: dict[str, Any],
    query_text: str,
    max_hits: int,
    char_limit_override: int | None = None,
) -> dict[str, Any]:
    out = dict(fractal_context)
    layers = out.get("layers") if isinstance(out.get("layers"), dict) else {}
    retrieval = select_fractal_long_term_hits(layers=layers, query_text=query_text, max_hits=max_hits)
    out["retrieval"] = retrieval
    base_dropped = [row for row in (out.get("dropped") or []) if isinstance(row, dict)]
    retrieval_dropped = [row for row in (retrieval.get("dropped") or []) if isinstance(row, dict)]
    if retrieval_dropped:
        base_dropped.extend(retrieval_dropped)
        out["dropped"] = base_dropped
        cfg_obj = out.get("config") if isinstance(out.get("config"), dict) else {}
        cfg_for_budget = FractalConfig(
            scene_window=max(1, int(cfg_obj.get("scene_window") or 5)),
            arc_window=max(1, int(cfg_obj.get("arc_window") or 5)),
            char_limit=max(0, int(cfg_obj.get("char_limit") or 6000)),
            recent_window_chapters=max(1, int(cfg_obj.get("recent_window_chapters") or 80)),
            mid_window_chapters=max(1, int(cfg_obj.get("mid_window_chapters") or 200)),
            long_window_chapters=max(1, int(cfg_obj.get("long_window_chapters") or 600)),
            long_index_terms=max(1, int(cfg_obj.get("long_index_terms") or 12)),
            long_retrieval_hits=max(1, int(cfg_obj.get("long_retrieval_hits") or 3)),
        )
        out["budget_observability"] = _fractal_budget_observability(
            config=cfg_for_budget,
            dropped=base_dropped,
            done_limit=int(cfg_obj.get("done_chapters_limit") or 0) if cfg_obj.get("done_chapters_limit") is not None else None,
        )

    if not retrieval.get("hits"):
        return out

    recent = layers.get("recent_window", {}) if isinstance(layers, dict) else {}
    recent_chapters = recent.get("chapters") if isinstance(recent, dict) and isinstance(recent.get("chapters"), list) else []
    mid_term = layers.get("mid_term", {}) if isinstance(layers, dict) else {}
    stages = mid_term.get("stages") if isinstance(mid_term, dict) and isinstance(mid_term.get("stages"), list) else []
    long_term = layers.get("long_term", {}) if isinstance(layers, dict) else {}
    outlines = long_term.get("outlines") if isinstance(long_term, dict) and isinstance(long_term.get("outlines"), list) else []

    latest_mid_stage = stages[-1] if stages and isinstance(stages[-1], dict) else None
    latest_long_outline = outlines[-1] if outlines and isinstance(outlines[-1], dict) else None
    prompt_inner = _build_fractal_prompt_inner(
        recent_chapters=[row for row in recent_chapters if isinstance(row, dict)],
        latest_mid_stage=latest_mid_stage if isinstance(latest_mid_stage, dict) else None,
        latest_long_outline=latest_long_outline if isinstance(latest_long_outline, dict) else None,
        long_hits=[row for row in retrieval.get("hits") or [] if isinstance(row, dict)],
    )
    cfg = out.get("config") if isinstance(out.get("config"), dict) else {}
    char_limit = int(char_limit_override) if char_limit_override is not None else int(cfg.get("char_limit") or 6000)
    prompt_inner = _clip_text(prompt_inner, limit=max(0, int(char_limit)))
    text_md = f"<FractalMemory>\n{prompt_inner}\n</FractalMemory>" if prompt_inner else ""
    out["prompt_block"] = {"identifier": "sys.memory.fractal", "role": "system", "text_md": text_md}
    out["text_md"] = text_md
    return out


def get_fractal_context(*, db: Session, project_id: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "disabled_reason": "disabled",
            "config": {},
            "layers": {},
            "scenes": [],
            "arcs": [],
            "sagas": [],
            "dropped": [],
            "budget_observability": {},
            "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": ""},
        }

    row = db.execute(select(FractalMemory).where(FractalMemory.project_id == project_id)).scalars().first()
    if row is None:
        return {
            "enabled": False,
            "disabled_reason": "not_built",
            "config": {},
            "layers": {},
            "scenes": [],
            "arcs": [],
            "sagas": [],
            "dropped": [],
            "budget_observability": {},
            "prompt_block": {"identifier": "sys.memory.fractal", "role": "system", "text_md": ""},
        }

    cfg = _safe_json_loads(row.config_json, default={})
    scenes = _safe_json_loads(row.scenes_json, default=[])
    arcs = _safe_json_loads(row.arcs_json, default=[])
    sagas = _safe_json_loads(row.sagas_json, default=[])
    cfg_dict = cfg if isinstance(cfg, dict) else {}
    layers_raw = cfg_dict.get("layered_archive")
    layers = layers_raw if isinstance(layers_raw, dict) else {}

    recent = layers.get("recent_window") if isinstance(layers, dict) else None
    recent_chapters = recent.get("chapters") if isinstance(recent, dict) and isinstance(recent.get("chapters"), list) else []
    mid_term = layers.get("mid_term") if isinstance(layers, dict) else None
    mid_stages = mid_term.get("stages") if isinstance(mid_term, dict) and isinstance(mid_term.get("stages"), list) else []
    long_term = layers.get("long_term") if isinstance(layers, dict) else None
    long_outlines = long_term.get("outlines") if isinstance(long_term, dict) and isinstance(long_term.get("outlines"), list) else []

    prompt_inner = _build_fractal_prompt_inner(
        recent_chapters=[row for row in recent_chapters if isinstance(row, dict)],
        latest_mid_stage=mid_stages[-1] if mid_stages and isinstance(mid_stages[-1], dict) else None,
        latest_long_outline=long_outlines[-1] if long_outlines and isinstance(long_outlines[-1], dict) else None,
        long_hits=None,
    )
    if not prompt_inner:
        latest = sagas[-1]["summary_md"] if isinstance(sagas, list) and sagas and isinstance(sagas[-1], dict) else ""
        prompt_inner = str(latest or "").strip()
    prompt_char_limit = max(0, int(cfg_dict.get("char_limit") or 6000))
    prompt_original_chars = len(prompt_inner)
    prompt_inner = _clip_text(prompt_inner, limit=prompt_char_limit)
    prompt_truncated = bool(prompt_char_limit > 0 and prompt_original_chars > prompt_char_limit)
    text_md = f"<FractalMemory>\n{prompt_inner}\n</FractalMemory>" if prompt_inner else ""

    dropped_cfg = cfg_dict.get("dropped")
    dropped = dropped_cfg if isinstance(dropped_cfg, list) else []
    budget_cfg = cfg_dict.get("budget_observability")
    if isinstance(budget_cfg, dict):
        budget_observability = budget_cfg
    else:
        cfg_for_budget = FractalConfig(
            scene_window=max(1, int(cfg_dict.get("scene_window") or 5)),
            arc_window=max(1, int(cfg_dict.get("arc_window") or 5)),
            char_limit=max(0, int(cfg_dict.get("char_limit") or 6000)),
            recent_window_chapters=max(1, int(cfg_dict.get("recent_window_chapters") or 80)),
            mid_window_chapters=max(1, int(cfg_dict.get("mid_window_chapters") or 200)),
            long_window_chapters=max(1, int(cfg_dict.get("long_window_chapters") or 600)),
            long_index_terms=max(1, int(cfg_dict.get("long_index_terms") or 12)),
            long_retrieval_hits=max(1, int(cfg_dict.get("long_retrieval_hits") or 3)),
        )
        budget_observability = _fractal_budget_observability(
            config=cfg_for_budget,
            dropped=[row for row in dropped if isinstance(row, dict)],
            done_limit=int(cfg_dict.get("done_chapters_limit") or 0) if cfg_dict.get("done_chapters_limit") is not None else None,
        )

    v2_cfg = cfg_dict.get("v2") if isinstance(cfg_dict, dict) else None
    v2_summary_md = str(v2_cfg.get("summary_md") or "").strip() if isinstance(v2_cfg, dict) else ""
    v2_text_md = f"<FractalMemoryV2>\n{v2_summary_md}\n</FractalMemoryV2>" if v2_summary_md else ""

    return {
        "enabled": True,
        "disabled_reason": None,
        "config": cfg_dict if isinstance(cfg_dict, dict) else {},
        "layers": layers if isinstance(layers, dict) else {},
        "v2": v2_cfg if isinstance(v2_cfg, dict) else {},
        "scenes": scenes if isinstance(scenes, list) else [],
        "arcs": arcs if isinstance(arcs, list) else [],
        "sagas": sagas if isinstance(sagas, list) else [],
        "dropped": dropped if isinstance(dropped, list) else [],
        "budget_observability": budget_observability if isinstance(budget_observability, dict) else {},
        "prompt_block": {
            "identifier": "sys.memory.fractal",
            "role": "system",
            "text_md": text_md,
            "truncated": bool(prompt_truncated),
            "char_limit": int(prompt_char_limit),
            "original_chars": int(prompt_original_chars),
        },
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
        recent_window_chapters=max(1, int(getattr(settings, "fractal_recent_window_chapters", 80) or 80)),
        mid_window_chapters=max(1, int(getattr(settings, "fractal_mid_window_chapters", 200) or 200)),
        long_window_chapters=max(1, int(getattr(settings, "fractal_long_window_chapters", 600) or 600)),
        long_index_terms=max(1, int(getattr(settings, "fractal_long_index_terms", 12) or 12)),
        long_retrieval_hits=max(1, int(getattr(settings, "fractal_long_retrieval_hits", 3) or 3)),
    )

    chapters = (
        db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.number.asc()))
        .scalars()
        .all()
    )

    done_chapters = [c for c in chapters if str(c.status or "").strip() == "done"]
    done_total = len(done_chapters)

    done_limit = max(1, int(getattr(settings, "fractal_done_chapters_per_rebuild", _DEFAULT_MAX_DONE_CHAPTERS_PER_REBUILD) or _DEFAULT_MAX_DONE_CHAPTERS_PER_REBUILD))
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
    dropped_items = [row for row in (computed.get("dropped") or []) if isinstance(row, dict)]
    if done_truncated:
        dropped_items.append({"reason": "done_chapters_budget", "count": max(1, done_total - len(done_chapters))})
    budget_obs = _fractal_budget_observability(config=cfg, dropped=dropped_items, done_limit=done_limit)
    row = db.execute(select(FractalMemory).where(FractalMemory.project_id == project_id)).scalars().first()
    if row is None:
        row = FractalMemory(id=new_id(), project_id=project_id)
        db.add(row)

    row.config_json = _compact_json_dumps(
        {
            "scene_window": cfg.scene_window,
            "arc_window": cfg.arc_window,
            "char_limit": cfg.char_limit,
            "recent_window_chapters": cfg.recent_window_chapters,
            "mid_window_chapters": cfg.mid_window_chapters,
            "long_window_chapters": cfg.long_window_chapters,
            "long_index_terms": cfg.long_index_terms,
            "long_retrieval_hits": cfg.long_retrieval_hits,
            "reason": reason,
            "done_chapters_total": done_total,
            "done_chapters_used": len(done_chapters),
            "done_chapters_limit": done_limit,
            "done_chapters_truncated": bool(done_truncated),
            "layered_archive": computed.get("layers") if isinstance(computed.get("layers"), dict) else {},
            "dropped": dropped_items,
            "budget_observability": budget_obs,
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
        counts={
            "scenes": len(out.get("scenes") or []),
            "arcs": len(out.get("arcs") or []),
            "sagas": len(out.get("sagas") or []),
            "mid_stages": len((out.get("layers") or {}).get("mid_term", {}).get("stages") or [])
            if isinstance(out.get("layers"), dict)
            else 0,
            "long_outlines": len((out.get("layers") or {}).get("long_term", {}).get("outlines") or [])
            if isinstance(out.get("layers"), dict)
            else 0,
        },
        timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
    )
    return out
