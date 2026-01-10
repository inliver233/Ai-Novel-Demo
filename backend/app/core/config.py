from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_abs_path(value: str) -> bool:
    if value.startswith("/"):
        return True
    if value.startswith("\\\\"):
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", value))


AppEnv = Literal["dev", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
TaskQueueBackend = Literal["rq", "inline"]
CookieSameSite = Literal["lax", "strict", "none"]
VectorBackend = Literal["auto", "chroma", "pgvector"]


class Settings(BaseSettings):
    app_env: AppEnv = "dev"
    log_level: LogLevel = "INFO"
    database_url: str = "sqlite:///./ainovel.db"
    cors_origins: str = "http://localhost:5173"
    app_version: str = "0.1.0"
    secret_encryption_key: str | None = None

    auth_session_signing_key: str | None = None
    auth_dev_fallback_user_id: str | None = "local-user"
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 7
    auth_refresh_threshold_seconds: int = 60 * 15
    auth_cookie_user_id_name: str = "user_id"
    auth_cookie_expire_at_name: str = "session_expire_at"
    auth_cookie_samesite: CookieSameSite = "lax"
    auth_admin_user_id: str | None = None
    auth_admin_password: str | None = None
    auth_admin_email: str | None = None
    auth_admin_display_name: str | None = "管理员"
    auth_bcrypt_rounds: int = 12

    task_queue_backend: TaskQueueBackend = "rq"
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "default"

    vector_chroma_persist_dir: str | None = None
    vector_embedding_base_url: str | None = None
    vector_embedding_model: str | None = None
    vector_embedding_api_key: str | None = None
    vector_backend: VectorBackend = "auto"
    vector_hybrid_enabled: bool = True
    vector_hybrid_rrf_k: int = 60
    vector_overfiltering_enabled: bool = True
    vector_max_candidates: int = 20
    vector_final_max_chunks: int = 6
    vector_final_char_limit: int = 6000
    vector_chunk_size: int = 800
    vector_chunk_overlap: int = 120

    fractal_enabled: bool = True
    fractal_scene_window: int = 5
    fractal_arc_window: int = 5
    fractal_char_limit: int = 6000

    model_config = SettingsConfigDict(
        env_file=str(_backend_dir() / ".env"),
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: object) -> str:
        raw = str(value).strip().lower()
        if raw in ("dev", "development"):
            return "dev"
        if raw in ("prod", "production"):
            return "prod"
        raise ValueError("APP_ENV must be 'dev' or 'prod'")

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> str:
        raw = str(value).strip().upper()
        if raw == "WARN":
            raw = "WARNING"
        if raw in ("DEBUG", "INFO", "WARNING", "ERROR"):
            return raw
        raise ValueError("LOG_LEVEL must be one of: DEBUG/INFO/WARNING/ERROR")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "sqlite:///./ainovel.db"

        try:
            url = make_url(raw)
        except Exception:
            return raw

        if url.get_backend_name() != "sqlite":
            return raw

        db = str(url.database or "").strip()
        if not db or db == ":memory:" or db.startswith("file:"):
            return raw

        if _is_abs_path(db):
            return raw

        abs_path = (_backend_dir() / db).resolve()
        return str(url.set(database=abs_path.as_posix()))

    @field_validator("secret_encryption_key", mode="before")
    @classmethod
    def _normalize_secret_encryption_key(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_session_signing_key", mode="before")
    @classmethod
    def _normalize_auth_session_signing_key(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_dev_fallback_user_id", mode="before")
    @classmethod
    def _normalize_auth_dev_fallback_user_id(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_session_ttl_seconds", mode="before")
    @classmethod
    def _normalize_auth_session_ttl_seconds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 60 * 60 * 24 * 7
        return raw

    @field_validator("auth_refresh_threshold_seconds", mode="before")
    @classmethod
    def _normalize_auth_refresh_threshold_seconds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 60 * 15
        return raw

    @field_validator("auth_cookie_user_id_name", mode="before")
    @classmethod
    def _normalize_auth_cookie_user_id_name(cls, value: object) -> str:
        raw = str(value or "").strip()
        return raw or "user_id"

    @field_validator("auth_cookie_expire_at_name", mode="before")
    @classmethod
    def _normalize_auth_cookie_expire_at_name(cls, value: object) -> str:
        raw = str(value or "").strip()
        return raw or "session_expire_at"

    @field_validator("auth_cookie_samesite", mode="before")
    @classmethod
    def _normalize_auth_cookie_samesite(cls, value: object) -> str:
        raw = str(value or "").strip().lower()
        if raw in ("lax", "strict", "none"):
            return raw
        return "lax"

    @field_validator("auth_admin_user_id", mode="before")
    @classmethod
    def _normalize_auth_admin_user_id(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_admin_password", mode="before")
    @classmethod
    def _normalize_auth_admin_password(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_admin_email", mode="before")
    @classmethod
    def _normalize_auth_admin_email(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_admin_display_name", mode="before")
    @classmethod
    def _normalize_auth_admin_display_name(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("auth_bcrypt_rounds", mode="before")
    @classmethod
    def _normalize_auth_bcrypt_rounds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 12
        if raw < 10:
            return 10
        if raw > 15:
            return 15
        return raw

    @field_validator("task_queue_backend", mode="before")
    @classmethod
    def _normalize_task_queue_backend(cls, value: object) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "rq"
        if raw in ("rq", "redis_rq"):
            return "rq"
        if raw in ("inline", "inprocess", "in_process"):
            return "inline"
        raise ValueError("TASK_QUEUE_BACKEND must be 'rq' or 'inline'")

    @field_validator("redis_url", mode="before")
    @classmethod
    def _normalize_redis_url(cls, value: object) -> str:
        raw = str(value or "").strip()
        return raw or "redis://localhost:6379/0"

    @field_validator("rq_queue_name", mode="before")
    @classmethod
    def _normalize_rq_queue_name(cls, value: object) -> str:
        raw = str(value or "").strip()
        return raw or "default"

    @field_validator("vector_chroma_persist_dir", mode="before")
    @classmethod
    def _normalize_vector_chroma_persist_dir(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if _is_abs_path(raw):
            return raw
        abs_path = (_backend_dir() / raw).resolve()
        return abs_path.as_posix()

    @field_validator("vector_embedding_base_url", mode="before")
    @classmethod
    def _normalize_vector_embedding_base_url(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("vector_embedding_model", mode="before")
    @classmethod
    def _normalize_vector_embedding_model(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("vector_embedding_api_key", mode="before")
    @classmethod
    def _normalize_vector_embedding_api_key(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("vector_max_candidates", mode="before")
    @classmethod
    def _normalize_vector_max_candidates(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 20
        return min(raw, 40)

    @field_validator("vector_final_max_chunks", mode="before")
    @classmethod
    def _normalize_vector_final_max_chunks(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 6
        return min(raw, 12)

    @field_validator("vector_final_char_limit", mode="before")
    @classmethod
    def _normalize_vector_final_char_limit(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 6000
        return min(raw, 20000)

    @field_validator("vector_chunk_size", mode="before")
    @classmethod
    def _normalize_vector_chunk_size(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 800
        return min(raw, 5000)

    @field_validator("vector_chunk_overlap", mode="before")
    @classmethod
    def _normalize_vector_chunk_overlap(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 120
        return min(raw, 1000)

    @model_validator(mode="after")
    def _validate_crypto_config(self) -> "Settings":
        if self.app_env == "prod" and not self.secret_encryption_key:
            raise ValueError("SECRET_ENCRYPTION_KEY must be set when APP_ENV=prod")
        if self.app_env == "prod" and self.task_queue_backend != "rq":
            raise ValueError("TASK_QUEUE_BACKEND must be set to 'rq' when APP_ENV=prod")
        if self.task_queue_backend == "rq" and not self.redis_url:
            raise ValueError("REDIS_URL must be set when TASK_QUEUE_BACKEND=rq")
        return self

    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def is_sqlite(self) -> bool:
        return self.database_url.strip().startswith("sqlite")


settings = Settings()
