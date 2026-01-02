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


class Settings(BaseSettings):
    app_env: AppEnv = "dev"
    log_level: LogLevel = "INFO"
    database_url: str = "sqlite:///./ainovel.db"
    cors_origins: str = "http://localhost:5173"
    app_version: str = "0.1.0"
    secret_encryption_key: str | None = None

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

    @model_validator(mode="after")
    def _validate_crypto_config(self) -> "Settings":
        if self.app_env == "prod" and not self.secret_encryption_key:
            raise ValueError("SECRET_ENCRYPTION_KEY must be set when APP_ENV=prod")
        return self

    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def is_sqlite(self) -> bool:
        return self.database_url.strip().startswith("sqlite")


settings = Settings()
