from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import LOCAL_USER_ID
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import AppError, error_payload
from app.core.logging import configure_logging, exception_log_fields, log_event
from app.core.request_id import new_request_id, set_request_id
from app.db.migrations import ensure_db_schema
from app.db.session import SessionLocal
from app.llm.http_client import close_llm_http_client
from app.models.user import User

logger = logging.getLogger("ainovel")


def _warn_sqlite_single_worker() -> None:
    if not settings.is_sqlite():
        return
    log_event(
        logger,
        "warning",
        sqlite={
            "database_url": settings.database_url,
            "constraint": "run with --workers 1",
        },
        message="SQLite 模式仅支持单 worker；请使用 `uvicorn ... --workers 1`（避免 database is locked）",
    )


def _safe_error_details(details: object | None) -> dict | None:
    if not isinstance(details, dict):
        return None
    allowlist = {
        "status_code",
        "upstream_error",
        "compat_adjustments",
        "compat_dropped_params",
        "errors",
    }
    safe = {k: v for k, v in details.items() if k in allowlist}
    return safe or None


def _ensure_local_user() -> None:
    db = SessionLocal()
    try:
        user = db.get(User, LOCAL_USER_ID)
        if user is None:
            db.add(User(id=LOCAL_USER_ID, display_name="本地用户"))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    ensure_db_schema()
    _warn_sqlite_single_worker()
    _ensure_local_user()
    yield
    close_llm_http_client()


app = FastAPI(title="ainovel", version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list() or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization", "X-LLM-Provider", "X-LLM-API-Key"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("X-Request-Id") or new_request_id()
    request.state.request_id = rid
    set_request_id(rid)

    start = time.perf_counter()
    response = await call_next(request)

    latency_ms = int((time.perf_counter() - start) * 1000)
    if response.status_code < 400:
        log_event(
            logger,
            "info",
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    rid = getattr(request.state, "request_id", new_request_id())
    log_event(
        logger,
        "warning" if exc.status_code < 500 else "error",
        path=request.url.path,
        method=request.method,
        status_code=exc.status_code,
        error_code=exc.code,
        message=exc.message,
        details=_safe_error_details(exc.details),
    )
    payload = error_payload(request_id=rid, code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(payload, status_code=exc.status_code, headers={"X-Request-Id": rid})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    rid = getattr(request.state, "request_id", new_request_id())
    safe_errors = [
        {k: v for k, v in e.items() if k in ("loc", "msg", "type")}
        for e in exc.errors()
        if isinstance(e, dict)
    ]
    log_event(
        logger,
        "warning",
        path=request.url.path,
        method=request.method,
        status_code=400,
        error_code="VALIDATION_ERROR",
        message="参数校验失败",
        details={"errors": safe_errors},
    )
    payload = error_payload(
        request_id=rid,
        code="VALIDATION_ERROR",
        message="参数校验失败",
        details={"errors": safe_errors},
    )
    return JSONResponse(payload, status_code=400, headers={"X-Request-Id": rid})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    rid = getattr(request.state, "request_id", new_request_id())
    log_event(
        logger,
        "error",
        path=request.url.path,
        method=request.method,
        status_code=500,
        error="DB_ERROR",
        **exception_log_fields(exc),
    )
    payload = error_payload(request_id=rid, code="DB_ERROR", message="数据库错误", details={})
    return JSONResponse(payload, status_code=500, headers={"X-Request-Id": rid})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", new_request_id())
    log_event(
        logger,
        "error",
        path=request.url.path,
        method=request.method,
        status_code=500,
        error="UNHANDLED_EXCEPTION",
        **exception_log_fields(exc),
    )
    payload = error_payload(request_id=rid, code="INTERNAL_ERROR", message="服务器内部错误", details={})
    return JSONResponse(payload, status_code=500, headers={"X-Request-Id": rid})

app.include_router(api_router)
