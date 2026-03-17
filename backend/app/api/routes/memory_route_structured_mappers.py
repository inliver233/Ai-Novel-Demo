from __future__ import annotations

from app.api.routes.memory_route_helpers import _safe_json
from app.models.structured_memory import MemoryEntity, MemoryEvidence, MemoryEvent, MemoryForeshadow, MemoryRelation


def _map_memory_entity_row(row: MemoryEntity) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "entity_type": row.entity_type,
        "name": row.name,
        "summary_md": row.summary_md,
        "attributes": _safe_json(row.attributes_json, {}),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _map_memory_relation_row(row: MemoryRelation) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "from_entity_id": row.from_entity_id,
        "to_entity_id": row.to_entity_id,
        "relation_type": row.relation_type,
        "description_md": row.description_md,
        "attributes": _safe_json(row.attributes_json, {}),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _map_memory_event_row(row: MemoryEvent) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "chapter_id": row.chapter_id,
        "event_type": row.event_type,
        "title": row.title,
        "content_md": row.content_md,
        "attributes": _safe_json(row.attributes_json, {}),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _map_memory_foreshadow_row(row: MemoryForeshadow) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "chapter_id": row.chapter_id,
        "resolved_at_chapter_id": row.resolved_at_chapter_id,
        "title": row.title,
        "content_md": row.content_md,
        "resolved": row.resolved,
        "attributes": _safe_json(row.attributes_json, {}),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _map_memory_evidence_row(row: MemoryEvidence) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "quote_md": row.quote_md,
        "attributes": _safe_json(row.attributes_json, {}),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "created_at": row.created_at.isoformat(),
    }
