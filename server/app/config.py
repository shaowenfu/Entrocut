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
    server_port: int = 8001
    server_log_level: str = "info"
    server_base_url: str = "http://127.0.0.1:8001"
    cors_allow_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174"
    )

    mongodb_uri: str | None = None
    mongodb_db_name: str = "entrocut_server"
    redis_url: str | None = "redis://127.0.0.1:6379/0"

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

    auth_google_client_id: str | None = None
    auth_google_client_secret: str | None = None
    auth_google_scope: str = "openid email profile"
    llm_proxy_mode: str = "mock"
    llm_default_model: str = "entro-reasoning-v1"
    llm_upstream_base_url: str | None = None
    llm_upstream_api_key: str | None = None
    llm_upstream_chat_path: str = "/v1/chat/completions"
    llm_upstream_default_model: str | None = None

    @property
    def allow_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def default_client_redirect_uri(self) -> str:
        return f"{self.auth_deep_link_scheme}://auth/callback"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
