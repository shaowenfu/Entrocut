from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "server/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.7.0-auth-phase1"
    rewrite_phase: str = "auth_phase1"
    app_env: str = "local"
    server_port: int = 8001
    server_log_level: str = "info"
    server_base_url: str = "http://127.0.0.1:8001"
    observability_enable_metrics: bool = True
    cors_allow_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174"
    )
    allow_inmemory_mongo_fallback: bool = True
    allow_inmemory_redis_fallback: bool = True

    mongodb_uri: str | None = None
    mongodb_db_name: str = "entrocut_server"
    redis_url: str | None = "redis://127.0.0.1:6379/0"
    quota_free_total_tokens: int = 200_000
    quota_low_watermark_tokens: int = 20_000
    rate_limit_requests_per_minute: int = 20
    rate_limit_tokens_per_minute: int = 40_000

    auth_jwt_algorithm: str = "HS256"
    auth_jwt_secret: str = "entrocut-dev-secret-change-me"
    auth_access_token_expires_seconds: int = 3600
    auth_refresh_token_expires_seconds: int = 60 * 60 * 24 * 30
    auth_login_session_ttl_seconds: int = 600
    auth_deep_link_scheme: str = "entrocut"
    auth_token_issuer: str = "entrocut-server"
    auth_token_audience: str = "entrocut-core"
    auth_dev_fallback_enabled: bool = True
    auth_dev_fallback_web_url: str = "http://127.0.0.1:5173/"
    staging_test_bootstrap_enabled: bool = False
    staging_test_bootstrap_secret: str | None = None

    auth_google_client_id: str | None = None
    auth_google_client_secret: str | None = None
    auth_github_client_id: str | None = None
    auth_github_client_secret: str | None = None
    auth_google_scope: str = "openid email profile"
    llm_proxy_mode: str = "mock"
    llm_default_model: str = "entro-reasoning-v1"
    google_api_key: str | None = None
    llm_gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_gemini_chat_path: str = "/chat/completions"
    llm_gemini_default_model: str = "gemini-2.5-flash"
    llm_upstream_base_url: str | None = None
    llm_upstream_api_key: str | None = None
    llm_upstream_chat_path: str = "/v1/chat/completions"
    llm_upstream_default_model: str | None = None

    # DashScope MultiModal Embedding
    dashscope_api_key: str | None = None
    dashscope_multimodal_embedding_model: str = "qwen3-vl-embedding"
    dashscope_multimodal_dimension: int = 1024

    # DashVector
    dashvector_api_key: str | None = None
    dashvector_endpoint: str | None = None
    dashvector_collection_name: str = "entrocut_assets"
    dashvector_partition: str = "default"
    dashvector_timeout_seconds: int = 10
    dashvector_protocol: str = "grpc"

    @property
    def allow_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def default_client_redirect_uri(self) -> str:
        return f"{self.auth_deep_link_scheme}://auth/callback"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def is_staging(self) -> bool:
        return self.app_env.strip().lower() == "staging"

    @property
    def requires_strict_runtime(self) -> bool:
        return self.is_production or self.is_staging


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
