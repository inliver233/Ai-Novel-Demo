from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.memory_pack import MemoryContextPackOut
from app.services.fractal_memory_service import get_fractal_context
from app.services.vector_rag_service import vector_rag_status
from app.services.worldbook_service import preview_worldbook_trigger


def retrieve_memory_context_pack(*, db: Session, project_id: str) -> MemoryContextPackOut:
    """
    Phase 0: empty implementation.

    Must be safe when memory dependencies (vector DB / embeddings / etc.) are missing.
    """
    worldbook_preview = preview_worldbook_trigger(
        db=db,
        project_id=project_id,
        query_text="",
        include_constant=True,
        enable_recursion=True,
        char_limit=12000,
    )

    placeholder_disabled_reason = "not_implemented"
    placeholder_note = "Phase 0 placeholder"

    worldbook = {**worldbook_preview.model_dump(), "enabled": True, "disabled_reason": None}
    story_memory: dict[str, Any] = {"enabled": False, "disabled_reason": placeholder_disabled_reason, "note": placeholder_note}
    structured: dict[str, Any] = {"enabled": False, "disabled_reason": placeholder_disabled_reason, "note": placeholder_note}
    graph: dict[str, Any] = {"enabled": False, "disabled_reason": placeholder_disabled_reason, "note": placeholder_note}

    vector_rag = vector_rag_status(project_id=project_id)
    fractal = get_fractal_context(db=db, project_id=project_id, enabled=bool(getattr(settings, "fractal_enabled", True)))

    logs: list[dict[str, Any]] = [
        {
            "section": "worldbook",
            "enabled": bool(worldbook.get("enabled")),
            "disabled_reason": worldbook.get("disabled_reason"),
            "note": "Phase 1: preview_worldbook_trigger (used by UI debug only)",
        },
        {
            "section": "story_memory",
            "enabled": bool(story_memory.get("enabled")),
            "disabled_reason": story_memory.get("disabled_reason"),
            "note": placeholder_note,
        },
        {
            "section": "structured",
            "enabled": bool(structured.get("enabled")),
            "disabled_reason": structured.get("disabled_reason"),
            "note": placeholder_note,
        },
        {
            "section": "vector_rag",
            "enabled": bool(vector_rag.get("enabled")),
            "disabled_reason": vector_rag.get("disabled_reason"),
            "note": "Phase 4A.1: use /api/projects/{project_id}/vector/query to run retrieval",
        },
        {
            "section": "graph",
            "enabled": bool(graph.get("enabled")),
            "disabled_reason": graph.get("disabled_reason"),
            "note": placeholder_note,
        },
        {
            "section": "fractal",
            "enabled": bool(fractal.get("enabled")),
            "disabled_reason": fractal.get("disabled_reason"),
            "note": "Phase 6.2: use /api/projects/{project_id}/fractal/rebuild to rebuild deterministically",
        },
    ]

    return MemoryContextPackOut.model_validate(
        {
            "worldbook": worldbook,
            "story_memory": story_memory,
            "structured": structured,
            "vector_rag": vector_rag,
            "graph": graph,
            "fractal": fractal,
            "logs": logs,
        }
    )


def placeholder_memory_retrieval_log(*, enabled: bool) -> dict[str, Any]:
    """
    Phase 0 placeholder for `memory_retrieval_log_json`.

    Spec reference: `长期记忆系统完整实现规划.md` §14.2.
    """
    return {
        "phase": "0.1",
        "enabled": bool(enabled),
        "query_text": "",
        "per_section": {},
        "budgets": {},
        "overfilter": {},
        "errors": [],
    }
