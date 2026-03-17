from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.worldbook_route_mappers import _parse_json_list
from app.api.routes.worldbook_route_models import WorldBookAutoUpdateTarget
from app.core.config import settings
from app.core.errors import AppError
from app.db.utils import utc_now
from app.models.chapter import Chapter
from app.models.project_settings import ProjectSettings
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.project_task_service import schedule_worldbook_auto_update_task
from app.services.worldbook_service import preview_worldbook_trigger


def _resolve_worldbook_auto_update_target(
    db: Session,
    *,
    project_id: str,
    chapter_id: str | None,
) -> WorldBookAutoUpdateTarget:
    chapter: Chapter | None = None
    if chapter_id is not None and str(chapter_id).strip():
        chapter = db.get(Chapter, str(chapter_id))
        if chapter is None or str(chapter.project_id) != str(project_id):
            raise AppError.not_found('章节不存在')
        if str(getattr(chapter, 'status', '') or '') != 'done':
            raise AppError.validation(details={'reason': 'chapter_not_done'})
    else:
        chapter = (
            db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.status == 'done',
                )
                .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    resolved_id = str(getattr(chapter, 'id', '') or '').strip() or None
    updated_at = getattr(chapter, 'updated_at', None) if chapter is not None else None
    token = (
        updated_at.isoformat().replace('+00:00', 'Z')
        if updated_at is not None
        else utc_now().isoformat().replace('+00:00', 'Z')
    )
    return WorldBookAutoUpdateTarget(chapter_id=resolved_id, chapter_token=token)


def _build_worldbook_auto_update_payload(
    db: Session,
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    chapter_id: str | None,
) -> dict[str, object]:
    target = _resolve_worldbook_auto_update_target(db, project_id=project_id, chapter_id=chapter_id)
    task_id = schedule_worldbook_auto_update_task(
        db=db,
        project_id=project_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        chapter_id=target.chapter_id,
        chapter_token=target.chapter_token,
        reason='manual_worldbook_auto_update',
    )
    if not task_id:
        raise AppError.validation(details={'reason': 'schedule_failed'})
    return {'task_id': task_id, 'chapter_id': target.chapter_id}


def _build_worldbook_preview_payload(
    db: Session,
    *,
    project_id: str,
    body: object,
) -> dict[str, object]:
    settings_row = db.get(ProjectSettings, project_id)
    qp_cfg = parse_query_preprocessing_config(
        (settings_row.query_preprocessing_json or '').strip() if settings_row is not None else None
    )
    normalized, preprocess_obs = normalize_query_text(query_text=body.query_text, config=qp_cfg)

    result = preview_worldbook_trigger(
        db=db,
        project_id=project_id,
        query_text=normalized,
        include_constant=body.include_constant,
        enable_recursion=body.enable_recursion,
        char_limit=body.char_limit,
    )
    payload = result.model_dump()
    payload['raw_query_text'] = body.query_text
    payload['normalized_query_text'] = normalized
    payload['preprocess_obs'] = preprocess_obs
    payload['match_config'] = {
        'alias_enabled': bool(getattr(settings, 'worldbook_match_alias_enabled', False)),
        'pinyin_enabled': bool(getattr(settings, 'worldbook_match_pinyin_enabled', False)),
        'regex_enabled': bool(getattr(settings, 'worldbook_match_regex_enabled', False)),
        'regex_allowlist_size': len(
            _parse_json_list(getattr(settings, 'worldbook_match_regex_allowlist_json', None))
        ),
        'max_triggered_entries': int(getattr(settings, 'worldbook_match_max_triggered_entries', 0) or 0),
    }
    return payload
