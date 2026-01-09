from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.generation_run import GenerationRun
from app.models.llm_profile import LLMProfile
from app.models.outline import Outline
from app.models.project import Project
from app.models.worldbook_entry import WorldBookEntry

LOCAL_USER_ID = "local-user"


def get_current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if isinstance(user_id, str) and user_id:
        return user_id
    raise AppError.unauthorized()


def get_authenticated_user_id(request: Request) -> str:
    user_id = getattr(request.state, "authenticated_user_id", None)
    if isinstance(user_id, str) and user_id:
        return user_id
    raise AppError.unauthorized()


DbDep = Annotated[Session, Depends(get_db)]
UserIdDep = Annotated[str, Depends(get_current_user_id)]
AuthenticatedUserIdDep = Annotated[str, Depends(get_authenticated_user_id)]


def require_owned_project(db: Session, *, project_id: str, user_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise AppError.not_found()
    return project


def require_owned_character(db: Session, *, character_id: str, user_id: str) -> Character:
    character = db.get(Character, character_id)
    if character is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=character.project_id, user_id=user_id)
    return character


def require_owned_chapter(db: Session, *, chapter_id: str, user_id: str) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=chapter.project_id, user_id=user_id)
    return chapter


def require_owned_outline(db: Session, *, outline_id: str, user_id: str) -> Outline:
    outline = db.get(Outline, outline_id)
    if outline is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=outline.project_id, user_id=user_id)
    return outline


def require_owned_llm_profile(db: Session, *, profile_id: str, user_id: str) -> LLMProfile:
    profile = db.get(LLMProfile, profile_id)
    if profile is None or profile.owner_user_id != user_id:
        raise AppError.not_found()
    return profile


def require_owned_generation_run(db: Session, *, run_id: str, user_id: str) -> GenerationRun:
    run = db.get(GenerationRun, run_id)
    if run is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=run.project_id, user_id=user_id)
    return run


def require_owned_worldbook_entry(db: Session, *, entry_id: str, user_id: str) -> WorldBookEntry:
    entry = db.get(WorldBookEntry, entry_id)
    if entry is None:
        raise AppError.not_found()
    require_owned_project(db, project_id=entry.project_id, user_id=user_id)
    return entry
