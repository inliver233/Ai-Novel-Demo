from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import DbDep, UserIdDep, require_project_viewer
from app.core.errors import ok_payload
from app.services.search_index_service import query_project_search

router = APIRouter()


class SearchQueryRequest(BaseModel):
    q: str = Field(max_length=200)
    sources: list[str] = Field(default_factory=list, max_length=50)
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10000)


@router.post("/projects/{project_id}/search/query")
def query_search(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: SearchQueryRequest) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    out = query_project_search(db=db, project_id=project_id, q=body.q, sources=body.sources, limit=body.limit, offset=body.offset)
    return ok_payload(request_id=request_id, data=out)

