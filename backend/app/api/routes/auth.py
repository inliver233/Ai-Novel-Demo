from __future__ import annotations

import secrets
from datetime import timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select

from app.api.deps import AuthenticatedUserIdDep, DbDep
from app.core.auth_session import build_session, clear_session_cookies, set_session_cookies
from app.core.config import settings
from app.core.errors import AppError, ok_payload
from app.db.utils import utc_now
from app.models.user import User
from app.models.user_password import UserPassword
from app.schemas.base import RequestModel
from app.services.auth_service import hash_password, verify_password

router = APIRouter()


def _user_public(user: User) -> dict:
    return {"id": user.id, "display_name": user.display_name, "is_admin": bool(user.is_admin)}


def _require_admin(db: DbDep, *, user_id: str) -> User:
    actor = db.get(User, user_id)
    if actor is None or not actor.is_admin:
        raise AppError.forbidden()
    return actor


def _user_admin_public(*, user: User, pwd: UserPassword | None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": bool(user.is_admin),
        "disabled": bool(getattr(pwd, "disabled_at", None) is not None),
        "password_updated_at": getattr(pwd, "password_updated_at", None),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }

class LocalLoginRequest(RequestModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LocalRegisterRequest(RequestModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class ChangePasswordRequest(RequestModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class DisableUserRequest(RequestModel):
    disabled: bool = True


class AdminCreateUserRequest(RequestModel):
    user_id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    is_admin: bool = False
    password: str | None = Field(default=None, max_length=256)


class AdminResetPasswordRequest(RequestModel):
    new_password: str | None = Field(default=None, max_length=256)


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


@router.post("/auth/local/register")
def local_register(request: Request, db: DbDep, body: LocalRegisterRequest) -> JSONResponse:
    request_id = request.state.request_id

    target_user_id = body.user_id.strip()
    if not target_user_id:
        raise AppError.validation("user_id 不能为空")

    admin_user_id = (settings.auth_admin_user_id or "").strip()
    if admin_user_id and target_user_id == admin_user_id:
        raise AppError.forbidden("该用户名已被系统保留，请联系管理员分配/重置")

    if db.get(User, target_user_id) is not None:
        raise AppError.conflict("用户已存在")

    email = (body.email or "").strip() or None
    display_name = (body.display_name or "").strip() or target_user_id
    user = User(id=target_user_id, email=email, display_name=display_name, is_admin=False)
    db.add(user)

    pwd = UserPassword(
        user_id=target_user_id,
        password_hash=hash_password(body.password),
        password_updated_at=utc_now(),
        disabled_at=None,
    )
    db.add(pwd)
    db.commit()

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
    _require_admin(db, user_id=user_id)

    pwd = db.get(UserPassword, target_user_id)
    if pwd is None:
        raise AppError.not_found()

    pwd.disabled_at = utc_now() if body.disabled else None
    db.commit()

    return ok_payload(request_id=request_id, data={})


@router.get("/auth/admin/users")
def list_users(request: Request, db: DbDep, user_id: AuthenticatedUserIdDep) -> dict:
    request_id = request.state.request_id
    _require_admin(db, user_id=user_id)

    rows = db.execute(select(User, UserPassword).join(UserPassword, UserPassword.user_id == User.id, isouter=True)).all()
    users = [_user_admin_public(user=u, pwd=p) for u, p in rows]
    users.sort(key=lambda x: str(x.get("id") or ""))
    return ok_payload(request_id=request_id, data={"users": users})


@router.post("/auth/admin/users")
def create_user(request: Request, db: DbDep, user_id: AuthenticatedUserIdDep, body: AdminCreateUserRequest) -> dict:
    request_id = request.state.request_id
    _require_admin(db, user_id=user_id)

    target_user_id = body.user_id.strip()
    if not target_user_id:
        raise AppError.validation("user_id 不能为空")
    if db.get(User, target_user_id) is not None:
        raise AppError.conflict("用户已存在")

    user = User(
        id=target_user_id,
        email=(body.email or "").strip() or None,
        display_name=(body.display_name or "").strip() or None,
        is_admin=bool(body.is_admin),
    )
    db.add(user)

    raw_password = (body.password or "").strip()
    generated_password: str | None = None
    if not raw_password:
        generated_password = secrets.token_urlsafe(12)
        raw_password = generated_password

    pwd = UserPassword(
        user_id=target_user_id,
        password_hash=hash_password(raw_password),
        password_updated_at=utc_now(),
        disabled_at=None,
    )
    db.add(pwd)
    db.commit()

    return ok_payload(
        request_id=request_id,
        data={"user": _user_admin_public(user=user, pwd=pwd), "temp_password": generated_password},
    )


@router.post("/auth/admin/users/{target_user_id}/password/reset")
def reset_user_password(
    request: Request,
    db: DbDep,
    user_id: AuthenticatedUserIdDep,
    target_user_id: str,
    body: AdminResetPasswordRequest,
) -> dict:
    request_id = request.state.request_id
    _require_admin(db, user_id=user_id)

    user = db.get(User, target_user_id)
    if user is None:
        raise AppError.not_found()

    raw_password = (body.new_password or "").strip()
    if not raw_password:
        raw_password = secrets.token_urlsafe(12)

    pwd = db.get(UserPassword, target_user_id)
    if pwd is None:
        pwd = UserPassword(user_id=target_user_id, password_hash="", password_updated_at=utc_now(), disabled_at=None)
        db.add(pwd)

    pwd.password_hash = hash_password(raw_password)
    pwd.password_updated_at = utc_now()
    db.commit()

    return ok_payload(request_id=request_id, data={"temp_password": raw_password})


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
