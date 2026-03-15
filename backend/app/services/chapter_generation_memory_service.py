from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.project_settings import ProjectSettings
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.services.chapter_generation_models import ChapterMemoryPreparation
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.memory_retrieval_service import build_memory_retrieval_log_json, retrieve_memory_context_pack


def resolve_memory_modules(raw_modules: dict[str, bool]) -> dict[str, bool]:
    return {
        "worldbook": bool(raw_modules.get("worldbook", True)),
        "story_memory": bool(raw_modules.get("story_memory", True)),
        "semantic_history": bool(raw_modules.get("semantic_history", False)),
        "foreshadow_open_loops": bool(raw_modules.get("foreshadow_open_loops", False)),
        "structured": bool(raw_modules.get("structured", True)),
        "tables": bool(raw_modules.get("tables", True)),
        "vector_rag": bool(raw_modules.get("vector_rag", True)),
        "graph": bool(raw_modules.get("graph", True)),
        "fractal": bool(raw_modules.get("fractal", True)),
    }

def prepare_chapter_memory_injection(
    *,
    db: Session,
    project_id: str,
    chapter: Chapter,
    body: ChapterGenerateRequest,
    settings_row: ProjectSettings | None,
    base_instruction: str,
    values: dict[str, object],
) -> ChapterMemoryPreparation:
    if not body.memory_injection_enabled:
        return ChapterMemoryPreparation(
            memory_pack=None,
            memory_injection_config=None,
            memory_retrieval_log_json=None,
        )

    memory_query_text = ""
    query_text_source = "auto"
    requested_query_text = str(body.memory_query_text or "").strip()
    if requested_query_text:
        memory_query_text = requested_query_text[:5000]
        query_text_source = "user"
    else:
        memory_query_text = base_instruction
        if chapter.plan:
            memory_query_text = f"{memory_query_text}\n\n{chapter.plan}".strip()
        memory_query_text = memory_query_text[:5000]

    memory_modules = resolve_memory_modules(body.memory_modules or {})
    raw_query_text = memory_query_text
    qp_cfg = parse_query_preprocessing_config(
        (settings_row.query_preprocessing_json or "").strip() if settings_row is not None else None
    )
    memory_query_text, preprocess_obs = normalize_query_text(query_text=raw_query_text, config=qp_cfg)

    pack = None
    pack_errors = None
    try:
        pack = retrieve_memory_context_pack(
            db=db,
            project_id=project_id,
            query_text=memory_query_text,
            section_enabled=memory_modules,
        )
    except Exception:
        pack = None
        pack_errors = ["memory_pack_error"]

    memory_pack = pack.model_dump() if pack is not None else None
    if memory_pack is not None:
        values["memory"] = memory_pack

    memory_injection_config: dict[str, object] = {
        "query_text": memory_query_text,
        "query_text_source": query_text_source,
        "modules": memory_modules,
        "raw_query_text": raw_query_text,
        "normalized_query_text": memory_query_text,
        "preprocess_obs": preprocess_obs,
    }
    memory_retrieval_log_json = build_memory_retrieval_log_json(
        enabled=True,
        query_text=memory_query_text,
        pack=pack,
        errors=pack_errors,
    )
    return ChapterMemoryPreparation(
        memory_pack=memory_pack,
        memory_injection_config=memory_injection_config,
        memory_retrieval_log_json=memory_retrieval_log_json,
    )

def build_memory_run_params_extra_json(
    *,
    style_resolution: dict[str, object],
    memory_injection_enabled: bool,
    memory_preparation: ChapterMemoryPreparation,
) -> dict[str, object]:
    params: dict[str, object] = {
        "style_resolution": style_resolution,
        "memory_injection_enabled": memory_injection_enabled,
    }
    if memory_injection_enabled and memory_preparation.memory_injection_config is not None:
        params["memory_injection_config"] = memory_preparation.memory_injection_config
        params["memory_retrieval_log_json"] = memory_preparation.memory_retrieval_log_json
    return params

