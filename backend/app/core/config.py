from __future__ import annotations

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


AppEnv = Literal["dev", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    app_env: AppEnv = "dev"
    log_level: LogLevel = "INFO"
    database_url: str = "sqlite:///./ainovel.db"
    cors_origins: str = "http://localhost:5173"
    app_version: str = "0.1.0"

    model_config = SettingsConfigDict(
        env_file=".env",
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

    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def is_sqlite(self) -> bool:
        return self.database_url.strip().startswith("sqlite")


settings = Settings()
