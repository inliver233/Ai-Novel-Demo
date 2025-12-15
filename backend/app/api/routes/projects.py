from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.models.project import Project
from app.schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter()


@router.get("/projects")
def list_projects(request: Request, db: DbDep, user_id: UserIdDep) -> dict:
    request_id = request.state.request_id
    projects = (
        db.execute(select(Project).where(Project.owner_user_id == user_id).order_by(Project.created_at.desc()))
        .scalars()
        .all()
    )
    return ok_payload(request_id=request_id, data={"projects": [ProjectOut.model_validate(p).model_dump() for p in projects]})


@router.post("/projects")
def create_project(request: Request, db: DbDep, user_id: UserIdDep, body: ProjectCreate) -> dict:
    request_id = request.state.request_id
    project = Project(
        id=new_id(),
        owner_user_id=user_id,
        name=body.name,
        genre=body.genre,
        logline=body.logline,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ok_payload(request_id=request_id, data={"project": ProjectOut.model_validate(project).model_dump()})


@router.get("/projects/{project_id}")
def get_project(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise AppError.not_found()
    return ok_payload(request_id=request_id, data={"project": ProjectOut.model_validate(project).model_dump()})


@router.put("/projects/{project_id}")
def update_project(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: ProjectUpdate) -> dict:
    request_id = request.state.request_id
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise AppError.not_found()

    if body.name is not None:
        project.name = body.name
    if body.genre is not None:
        project.genre = body.genre
    if body.logline is not None:
        project.logline = body.logline

    db.commit()
    db.refresh(project)
    return ok_payload(request_id=request_id, data={"project": ProjectOut.model_validate(project).model_dump()})


@router.delete("/projects/{project_id}")
def delete_project(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise AppError.not_found()
    db.delete(project)
    db.commit()
    return ok_payload(request_id=request_id, data={})

