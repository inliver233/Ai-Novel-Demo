from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_chapter_editor, require_chapter_viewer
from app.core.errors import ok_payload
from app.core.logging import log_event
from app.models.story_memory import StoryMemory
from app.schemas.chapter_analysis import ChapterAnalyzeRequest, ChapterAnalysisApplyRequest, ChapterRewriteRequest
from app.services.annotations_service import build_annotations_from_story_memories
from app.services.chapter_analysis_app_service import analyze_chapter as analyze_chapter_service
from app.services.chapter_analysis_app_service import rewrite_chapter as rewrite_chapter_service
from app.services.plot_analysis_service import apply_chapter_analysis as apply_plot_analysis

router = APIRouter()
logger = logging.getLogger("ainovel")


@router.post("/chapters/{chapter_id}/analyze")
def analyze_chapter(
    request: Request,
    chapter_id: str,
    body: ChapterAnalyzeRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    data = analyze_chapter_service(
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    return ok_payload(request_id=request_id, data=data)


@router.post("/chapters/{chapter_id}/rewrite")
def rewrite_chapter(
    request: Request,
    chapter_id: str,
    body: ChapterRewriteRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    data = rewrite_chapter_service(
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    return ok_payload(request_id=request_id, data=data)


@router.post("/chapters/{chapter_id}/analysis/apply")
def apply_chapter_analysis_route(
    request: Request,
    db: DbDep,
    chapter_id: str,
    body: ChapterAnalysisApplyRequest,
    user_id: UserIdDep,
) -> dict:
    request_id = request.state.request_id
    chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
    content_md = body.draft_content_md if body.draft_content_md is not None else (chapter.content_md or "")

    out = apply_plot_analysis(
        db=db,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=chapter.project_id,
        chapter_id=chapter_id,
        chapter_number=int(chapter.number),
        analysis=body.analysis,
        draft_content_md=content_md,
    )
    return ok_payload(request_id=request_id, data=out)


@router.get("/chapters/{chapter_id}/annotations")
def get_chapter_annotations(
    request: Request,
    db: DbDep,
    chapter_id: str,
    user_id: UserIdDep,
) -> dict:
    request_id = request.state.request_id
    chapter = require_chapter_viewer(db, chapter_id=chapter_id, user_id=user_id)

    memories = (
        db.execute(
            select(StoryMemory)
            .where(StoryMemory.project_id == chapter.project_id, StoryMemory.chapter_id == chapter_id)
            .order_by(StoryMemory.importance_score.desc(), StoryMemory.created_at.asc())
        )
        .scalars()
        .all()
    )

    annotations, stats = build_annotations_from_story_memories(memories, content_md=chapter.content_md or "")
    if stats.get("need_fallback") or stats.get("clamped"):
        log_event(
            logger,
            "info",
            annotations={
                "chapter_id": chapter_id,
                "need_fallback": stats.get("need_fallback", 0),
                "attempted": stats.get("attempted", 0),
                "found": stats.get("found", 0),
                "clamped": stats.get("clamped", 0),
            },
        )

    return ok_payload(request_id=request_id, data={"annotations": annotations})
