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
    pack = MemoryContextPackOut()

    worldbook_preview = preview_worldbook_trigger(
        db=db,
        project_id=project_id,
        query_text="",
        include_constant=True,
        enable_recursion=True,
        char_limit=12000,
    )
    pack.worldbook = {"enabled": True, **worldbook_preview.model_dump()}

    pack.vector_rag = vector_rag_status(project_id=project_id)
    pack.logs.append(
        {
            "section": "vector_rag",
            "enabled": bool(pack.vector_rag.get("enabled")),
            "disabled_reason": pack.vector_rag.get("disabled_reason"),
            "note": "Phase 4A.1: use /api/projects/{project_id}/vector/query to run retrieval",
        }
    )

    pack.fractal = get_fractal_context(db=db, project_id=project_id, enabled=bool(getattr(settings, "fractal_enabled", True)))
    pack.logs.append(
        {
            "section": "fractal",
            "enabled": bool(pack.fractal.get("enabled")),
            "disabled_reason": pack.fractal.get("disabled_reason"),
            "note": "Phase 6.2: use /api/projects/{project_id}/fractal/rebuild to rebuild deterministically",
        }
    )
    return pack


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
