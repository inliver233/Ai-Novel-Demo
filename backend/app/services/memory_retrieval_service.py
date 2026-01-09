from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.memory_pack import MemoryContextPackOut


def retrieve_memory_context_pack(*, db: Session, project_id: str) -> MemoryContextPackOut:
    """
    Phase 0: empty implementation.

    Must be safe when memory dependencies (vector DB / embeddings / etc.) are missing.
    """
    _ = db
    _ = project_id
    return MemoryContextPackOut()


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

