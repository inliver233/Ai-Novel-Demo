from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.errors import ok_payload
from app.services.task_queue import get_queue_status_for_health

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    request_id = request.state.request_id
    return ok_payload(
        request_id=request_id,
        data={
            "status": "healthy",
            "version": settings.app_version,
            **get_queue_status_for_health(),
        },
    )
