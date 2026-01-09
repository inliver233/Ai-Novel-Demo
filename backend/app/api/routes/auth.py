from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import AuthenticatedUserIdDep, DbDep
from app.core.auth_session import build_session, clear_session_cookies, set_session_cookies
from app.core.config import settings
from app.core.errors import AppError, ok_payload
from app.db.utils import utc_now
from app.models.user import User
from app.models.user_password import UserPassword
from app.services.auth_service import hash_password, verify_password

router = APIRouter()


def _user_public(user: User) -> dict:
    return {"id": user.id, "display_name": user.display_name, "is_admin": bool(user.is_admin)}


class LocalLoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class DisableUserRequest(BaseModel):
    disabled: bool = True


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
def local_login(request: Request, db: DbDep, body: LocalLoginRequest) -> JSONResponse:
    request_id = request.state.request_id
    user = db.get(User, body.user_id)
    pwd = db.get(UserPassword, body.user_id)
    if user is None or pwd is None:
        raise AppError.unauthorized("用户名或密码错误")
    if pwd.disabled_at is not None:
        raise AppError.unauthorized("账号已禁用")
    if not verify_password(body.password, pwd.password_hash):
        raise AppError.unauthorized("用户名或密码错误")

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


@router.post("/auth/password/change")
def change_password(request: Request, db: DbDep, user_id: AuthenticatedUserIdDep, body: ChangePasswordRequest) -> dict:
    request_id = request.state.request_id
    pwd = db.get(UserPassword, user_id)
    if pwd is None or pwd.disabled_at is not None:
        raise AppError.unauthorized()
    if not verify_password(body.old_password, pwd.password_hash):
        raise AppError.unauthorized("旧密码错误")

    pwd.password_hash = hash_password(body.new_password)
    pwd.password_updated_at = utc_now()
    db.commit()

    return ok_payload(request_id=request_id, data={})


@router.post("/auth/admin/users/{target_user_id}/disable")
def set_user_disabled(
    request: Request,
    db: DbDep,
    user_id: AuthenticatedUserIdDep,
    target_user_id: str,
    body: DisableUserRequest,
) -> dict:
    request_id = request.state.request_id
    actor = db.get(User, user_id)
    if actor is None or not actor.is_admin:
        raise AppError.forbidden()

    pwd = db.get(UserPassword, target_user_id)
    if pwd is None:
        raise AppError.not_found()

    pwd.disabled_at = utc_now() if body.disabled else None
    db.commit()

    return ok_payload(request_id=request_id, data={})


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
