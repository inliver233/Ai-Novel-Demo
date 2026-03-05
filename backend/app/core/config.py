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
VectorChromaCollectionNaming = Literal["legacy", "hash"]
VectorEmbeddingProvider = Literal[
    "openai_compatible",
    "azure_openai",
    "google",
    "custom",
    "local_proxy",
    "sentence_transformers",
]


class Settings(BaseSettings):
    app_env: AppEnv = "dev"
    log_level: LogLevel = "INFO"
    database_url: str = "sqlite:///./ainovel.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800
    cors_origins: str = "http://localhost:5173"
    app_version: str = "0.1.0"
    secret_encryption_key: str | None = None

    auth_session_signing_key: str | None = None
    auth_dev_fallback_user_id: str | None = "local-user"
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 7
    auth_refresh_threshold_seconds: int = 60 * 15
    auth_activity_touch_interval_seconds: int = 30
    auth_online_window_seconds: int = 60 * 5
    auth_cookie_user_id_name: str = "user_id"
    auth_cookie_expire_at_name: str = "session_expire_at"
    auth_cookie_samesite: CookieSameSite = "lax"
    auth_admin_user_id: str | None = None
    auth_admin_password: str | None = None
    auth_admin_email: str | None = None
    auth_admin_display_name: str | None = "管理员"
    auth_bcrypt_rounds: int = 12

    linuxdo_oidc_discovery_url: str = "https://connect.linux.do/.well-known/openid-configuration"
    linuxdo_oidc_client_id: str | None = None
    linuxdo_oidc_client_secret: str | None = None
    linuxdo_oidc_scopes: str = "openid profile email"
    linuxdo_oidc_redirect_uri: str | None = None

    task_queue_backend: TaskQueueBackend = "rq"
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "default"

    vector_chroma_persist_dir: str | None = None
    vector_chroma_collection_naming: VectorChromaCollectionNaming = "hash"
    vector_embedding_provider: VectorEmbeddingProvider = "openai_compatible"
    vector_embedding_base_url: str | None = None
    vector_embedding_model: str | None = None
    vector_embedding_api_key: str | None = None
    vector_embedding_azure_deployment: str | None = None
    vector_embedding_azure_api_version: str | None = None
    vector_embedding_sentence_transformers_model: str | None = None
    vector_embedding_sentence_transformers_cache_dir: str | None = None
    vector_embedding_sentence_transformers_device: str | None = None
    vector_backend: VectorBackend = "auto"
    vector_hybrid_enabled: bool = True
    vector_priority_retrieval_enabled: bool = False
    vector_rerank_enabled: bool = False
    vector_rerank_external_base_url: str | None = None
    vector_rerank_external_model: str | None = None
    vector_rerank_external_api_key: str | None = None
    vector_rerank_external_timeout_seconds: float = 15.0
    vector_hybrid_rrf_k: int = 60
    vector_overfiltering_enabled: bool = True
    vector_max_candidates: int = 20
    vector_final_max_chunks: int = 6
    vector_per_source_id_max_chunks: int = 1
    vector_final_char_limit: int = 6000
    vector_chunk_size: int = 800
    vector_chunk_overlap: int = 120
    vector_source_order: str | None = None
    vector_source_weights_json: str | None = None

    worldbook_match_alias_enabled: bool = False
    worldbook_match_pinyin_enabled: bool = False
    worldbook_match_regex_enabled: bool = False
    worldbook_match_regex_allowlist_json: str | None = None
    worldbook_match_max_triggered_entries: int = 40

    glossary_query_expand_enabled: bool = False

    graph_max_hop: int = 1
    graph_max_nodes: int = 200
    graph_max_edges: int = 500
    graph_prompt_char_limit: int = 6000
    graph_match_entity_alias_candidates_limit: int = 2000

    fractal_enabled: bool = True
    fractal_scene_window: int = 5
    fractal_arc_window: int = 5
    fractal_char_limit: int = 6000
    fractal_done_chapters_per_rebuild: int = 1000
    fractal_recent_window_chapters: int = 80
    fractal_mid_window_chapters: int = 200
    fractal_long_window_chapters: int = 600
    fractal_long_index_terms: int = 12
    fractal_long_retrieval_hits: int = 3

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

    @field_validator("db_pool_size", mode="before")
    @classmethod
    def _normalize_db_pool_size(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 5
        return min(raw, 50)

    @field_validator("db_max_overflow", mode="before")
    @classmethod
    def _normalize_db_max_overflow(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw < 0:
            return 0
        return min(raw, 200)

    @field_validator("db_pool_timeout_seconds", mode="before")
    @classmethod
    def _normalize_db_pool_timeout_seconds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 30
        return min(raw, 120)

    @field_validator("db_pool_recycle_seconds", mode="before")
    @classmethod
    def _normalize_db_pool_recycle_seconds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 1800
        return min(raw, 24 * 60 * 60)

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

    @field_validator("auth_activity_touch_interval_seconds", mode="before")
    @classmethod
    def _normalize_auth_activity_touch_interval_seconds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 30
        return min(raw, 3600)

    @field_validator("auth_online_window_seconds", mode="before")
    @classmethod
    def _normalize_auth_online_window_seconds(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 60 * 5
        return min(raw, 24 * 60 * 60)

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

    @field_validator("linuxdo_oidc_discovery_url", mode="before")
    @classmethod
    def _normalize_linuxdo_oidc_discovery_url(cls, value: object) -> str:
        raw = str(value or "").strip()
        return raw or "https://connect.linux.do/.well-known/openid-configuration"

    @field_validator("linuxdo_oidc_client_id", mode="before")
    @classmethod
    def _normalize_linuxdo_oidc_client_id(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("linuxdo_oidc_client_secret", mode="before")
    @classmethod
    def _normalize_linuxdo_oidc_client_secret(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("linuxdo_oidc_scopes", mode="before")
    @classmethod
    def _normalize_linuxdo_oidc_scopes(cls, value: object) -> str:
        raw = str(value or "").strip()
        return raw or "openid profile email"

    @field_validator("linuxdo_oidc_redirect_uri", mode="before")
    @classmethod
    def _normalize_linuxdo_oidc_redirect_uri(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

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

    @field_validator("vector_chroma_collection_naming", mode="before")
    @classmethod
    def _normalize_vector_chroma_collection_naming(cls, value: object) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "hash"
        if raw in ("legacy", "hash"):
            return raw
        raise ValueError("VECTOR_CHROMA_COLLECTION_NAMING must be legacy|hash")

    @field_validator("vector_embedding_provider", mode="before")
    @classmethod
    def _normalize_vector_embedding_provider(cls, value: object) -> str:
        raw = str(value or "").strip().lower().replace("-", "_")
        if not raw:
            return "openai_compatible"
        aliases = {
            "openai": "openai_compatible",
            "openai_compat": "openai_compatible",
            "azure": "azure_openai",
            "azure_openai": "azure_openai",
            "google": "google",
            "gemini": "google",
            "custom": "custom",
            "local_proxy": "local_proxy",
            "sentence_transformers": "sentence_transformers",
            "sentence_transformer": "sentence_transformers",
            "st": "sentence_transformers",
        }
        normalized = aliases.get(raw, raw)
        if normalized not in (
            "openai_compatible",
            "azure_openai",
            "google",
            "custom",
            "local_proxy",
            "sentence_transformers",
        ):
            raise ValueError(
                "VECTOR_EMBEDDING_PROVIDER must be openai_compatible|azure_openai|google|custom|local_proxy|sentence_transformers"
            )
        return normalized

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

    @field_validator("vector_embedding_azure_deployment", mode="before")
    @classmethod
    def _normalize_vector_embedding_azure_deployment(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("vector_embedding_azure_api_version", mode="before")
    @classmethod
    def _normalize_vector_embedding_azure_api_version(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("vector_embedding_sentence_transformers_model", mode="before")
    @classmethod
    def _normalize_vector_embedding_sentence_transformers_model(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        return raw or None

    @field_validator("vector_embedding_sentence_transformers_cache_dir", mode="before")
    @classmethod
    def _normalize_vector_embedding_sentence_transformers_cache_dir(cls, value: object) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if _is_abs_path(raw):
            return raw
        abs_path = (_backend_dir() / raw).resolve()
        return abs_path.as_posix()

    @field_validator("vector_embedding_sentence_transformers_device", mode="before")
    @classmethod
    def _normalize_vector_embedding_sentence_transformers_device(cls, value: object) -> str | None:
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

    @field_validator("graph_max_hop", mode="before")
    @classmethod
    def _normalize_graph_max_hop(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 1
        return min(raw, 2)

    @field_validator("graph_max_nodes", mode="before")
    @classmethod
    def _normalize_graph_max_nodes(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 200
        return min(raw, 2000)

    @field_validator("graph_max_edges", mode="before")
    @classmethod
    def _normalize_graph_max_edges(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw < 0:
            return 500
        return min(raw, 5000)

    @field_validator("graph_prompt_char_limit", mode="before")
    @classmethod
    def _normalize_graph_prompt_char_limit(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 6000
        return min(raw, 50000)

    @field_validator("graph_match_entity_alias_candidates_limit", mode="before")
    @classmethod
    def _normalize_graph_match_entity_alias_candidates_limit(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 2000
        return min(raw, 10000)

    @field_validator("fractal_scene_window", mode="before")
    @classmethod
    def _normalize_fractal_scene_window(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 5
        return min(raw, 50)

    @field_validator("fractal_arc_window", mode="before")
    @classmethod
    def _normalize_fractal_arc_window(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 5
        return min(raw, 50)

    @field_validator("fractal_char_limit", mode="before")
    @classmethod
    def _normalize_fractal_char_limit(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 6000
        return min(raw, 40000)

    @field_validator("fractal_done_chapters_per_rebuild", mode="before")
    @classmethod
    def _normalize_fractal_done_chapters_per_rebuild(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 1000
        return min(raw, 5000)

    @field_validator("fractal_recent_window_chapters", mode="before")
    @classmethod
    def _normalize_fractal_recent_window_chapters(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 80
        return min(raw, 500)

    @field_validator("fractal_mid_window_chapters", mode="before")
    @classmethod
    def _normalize_fractal_mid_window_chapters(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 200
        return min(raw, 1000)

    @field_validator("fractal_long_window_chapters", mode="before")
    @classmethod
    def _normalize_fractal_long_window_chapters(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 600
        return min(raw, 5000)

    @field_validator("fractal_long_index_terms", mode="before")
    @classmethod
    def _normalize_fractal_long_index_terms(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 12
        return min(raw, 64)

    @field_validator("fractal_long_retrieval_hits", mode="before")
    @classmethod
    def _normalize_fractal_long_retrieval_hits(cls, value: object) -> int:
        try:
            raw = int(str(value or "").strip() or 0)
        except Exception:
            raw = 0
        if raw <= 0:
            return 3
        return min(raw, 20)

    @model_validator(mode="after")
    def _validate_crypto_config(self) -> "Settings":
        if self.app_env == "prod" and not self.secret_encryption_key:
            raise ValueError("SECRET_ENCRYPTION_KEY must be set when APP_ENV=prod")
        if self.app_env == "prod" and self.auth_dev_fallback_user_id:
            raise ValueError("AUTH_DEV_FALLBACK_USER_ID must be empty when APP_ENV=prod")
        if self.app_env == "prod" and self.task_queue_backend != "rq":
            raise ValueError("TASK_QUEUE_BACKEND must be set to 'rq' when APP_ENV=prod")
        if self.app_env == "prod":
            origins = self.cors_origins_list()
            if any(origin == "*" for origin in origins):
                raise ValueError("CORS_ORIGINS must not contain '*' when APP_ENV=prod")
            if any(origin.lower() == "null" for origin in origins):
                raise ValueError("CORS_ORIGINS must not contain 'null' when APP_ENV=prod")
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
