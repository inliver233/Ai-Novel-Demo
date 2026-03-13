from __future__ import annotations

import time

from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.utils import new_id
from app.models.generation_run import GenerationRun
from app.services.user_usage_service import bump_user_generation_usage, count_generated_chars


def _is_user_usage_insert_race(exc: IntegrityError) -> bool:
    text = str(exc).lower()
    if "user_usage_stats" not in text:
        return False
    return ("unique constraint" in text or "duplicate key value violates unique constraint" in text) and (
        "user_id" in text or "pkey" in text
    )


def write_generation_run(
    *,
    run_id: str | None = None,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    run_type: str,
    provider: str | None,
    model: str | None,
    prompt_system: str,
    prompt_user: str,
    prompt_render_log_json: str | None,
    params_json: str,
    output_text: str | None,
    error_json: str | None,
) -> str:
    """
    Persist a generation run using an independent session.

    Rationale: generation requests often hold a long-lived transaction (prompt rendering, LLM call, etc.).
    Writing runs in a separate short-lived session avoids coupling the audit trail to the request session lifecycle.
    """
    rid = run_id or new_id()
    generated_chars = count_generated_chars(output_text)
    had_error = bool(str(error_json or "").strip())
    retry_delays = (0.05, 0.1)
    for attempt in range(len(retry_delays) + 1):
        with SessionLocal() as db:
            try:
                db.add(
                    GenerationRun(
                        id=rid,
                        project_id=project_id,
                        actor_user_id=actor_user_id,
                        chapter_id=chapter_id,
                        type=run_type,
                        provider=provider,
                        model=model,
                        request_id=request_id,
                        prompt_system=prompt_system,
                        prompt_user=prompt_user,
                        prompt_render_log_json=prompt_render_log_json,
                        params_json=params_json,
                        output_text=output_text,
                        error_json=error_json,
                    )
                )
                bump_user_generation_usage(
                    db,
                    user_id=actor_user_id,
                    generated_chars=generated_chars,
                    had_error=had_error,
                )
                db.commit()
                return rid
            except IntegrityError as exc:
                db.rollback()
                if attempt < len(retry_delays) and _is_user_usage_insert_race(exc):
                    time.sleep(retry_delays[attempt])
                    continue
                raise
            except Exception:
                db.rollback()
                raise
    return rid
