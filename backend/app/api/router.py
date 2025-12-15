from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    chapters,
    characters,
    export,
    generation_runs,
    health,
    llm,
    llm_preset,
    outline,
    projects,
    prompts,
    settings,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(characters.router, tags=["characters"])
api_router.include_router(outline.router, tags=["outline"])
api_router.include_router(chapters.router, tags=["chapters"])
api_router.include_router(prompts.router, tags=["prompts"])
api_router.include_router(llm_preset.router, tags=["llm_preset"])
api_router.include_router(llm.router, tags=["llm"])
api_router.include_router(export.router, tags=["export"])
api_router.include_router(generation_runs.router, tags=["generation_runs"])
