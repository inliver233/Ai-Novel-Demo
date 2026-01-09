from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import AuthenticatedUserIdDep, DbDep, LOCAL_USER_ID
from app.core.auth_session import build_session, clear_session_cookies, set_session_cookies
from app.core.config import settings
from app.core.errors import AppError, ok_payload
from app.db.utils import utc_now
from app.models.user import User

router = APIRouter()


def _user_public(user: User) -> dict:
    return {"id": user.id, "display_name": user.display_name}


@router.get("/auth/user")
def get_current_user(request: Request, db: DbDep, user_id: AuthenticatedUserIdDep) -> dict:
    request_id = request.state.request_id
    user = db.get(User, user_id)
    if user is None:
        raise AppError.unauthorized()

    expires_at = getattr(request.state, "session_expire_at", None)
    session_payload = None
    if expires_at is not None:
        session_payload = {"expire_at": int(expires_at.astimezone(timezone.utc).timestamp())}

    return ok_payload(request_id=request_id, data={"user": _user_public(user), "session": session_payload})


@router.post("/auth/local/login")
def local_login(request: Request, db: DbDep) -> JSONResponse:
    if settings.app_env != "dev":
        raise AppError.forbidden("该端点仅用于本地开发")

    request_id = request.state.request_id
    user = db.get(User, LOCAL_USER_ID)
    if user is None:
        user = User(id=LOCAL_USER_ID, display_name="本地用户")
        db.add(user)
        db.commit()
        db.refresh(user)

    session = build_session(user_id=user.id)
    response = JSONResponse(
        ok_payload(
            request_id=request_id,
            data={
                "user": _user_public(user),
                "session": {"expire_at": int(session.expires_at.astimezone(timezone.utc).timestamp())},
            },
        )
    )
    set_session_cookies(response, user_id=user.id, expires_at=session.expires_at)
    return response


@router.post("/auth/refresh")
def refresh_session(request: Request, user_id: AuthenticatedUserIdDep) -> JSONResponse:
    request_id = request.state.request_id
    expires_at = getattr(request.state, "session_expire_at", None)
    if expires_at is None:
        raise AppError.unauthorized()

    now = utc_now()
    remaining_seconds = int((expires_at - now).total_seconds())

    refreshed = False
    out_expires_at = expires_at
    if remaining_seconds <= settings.auth_refresh_threshold_seconds:
        refreshed = True
        out_expires_at = now + timedelta(seconds=settings.auth_session_ttl_seconds)

    response = JSONResponse(
        ok_payload(
            request_id=request_id,
            data={
                "refreshed": refreshed,
                "session": {"expire_at": int(out_expires_at.astimezone(timezone.utc).timestamp())},
            },
        )
    )
    if refreshed:
        set_session_cookies(response, user_id=user_id, expires_at=out_expires_at)
    return response


@router.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    request_id = request.state.request_id
    response = JSONResponse(ok_payload(request_id=request_id, data={}))
    clear_session_cookies(response)
    return response

