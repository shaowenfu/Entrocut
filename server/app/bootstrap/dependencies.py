from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import Header

from ..core.config import RATE_CARDS, Settings, get_settings
from ..core.errors import ServerApiError
from ..core.observability import MetricsRegistry, configure_logging
from ..repositories.auth_store import AuthStore
from ..services.auth import OAuthService, TokenService, UserService
from ..services.gateway.provider_routing import effective_llm_proxy_mode, resolve_chat_provider
from ..services.inspect import InspectService
from ..services.quota import QuotaService, RateLimitService
from ..services.vector import VectorService


def request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)
metrics = MetricsRegistry()
store = AuthStore(settings)
oauth_service = OAuthService(settings, store)
user_service = UserService(store)
token_service = TokenService(settings, store)
quota_service = QuotaService(settings, store)
rate_limit_service = RateLimitService(settings)
vector_service = VectorService(settings)
inspect_service = InspectService(settings)


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_MISSING",
            message="Authorization header is required.",
            error_type="auth_error",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_INVALID",
            message="Authorization header must be a Bearer token.",
            error_type="auth_error",
        )
    return token.strip()


def bootstrap_secret(secret: str | None) -> str:
    if not settings.is_staging or not settings.staging_test_bootstrap_enabled:
        raise ServerApiError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="Staging test bootstrap is disabled.",
            error_type="invalid_request_error",
        )
    expected_secret = (settings.staging_test_bootstrap_secret or "").strip()
    if not expected_secret:
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="STAGING_TEST_BOOTSTRAP_SECRET is not configured.",
            error_type="server_error",
        )
    if (secret or "").strip() != expected_secret:
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_INVALID",
            message="Invalid staging bootstrap secret.",
            error_type="auth_error",
        )
    return expected_secret


def dependency_status(
    ok: bool,
    *,
    configured: bool,
    mode: str,
    required: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "configured": configured,
        "ok": ok,
        "mode": mode,
        "required": required,
    }
    if error:
        payload["error"] = error
    return payload


def provider_dependency_status() -> dict[str, Any]:
    proxy_mode = effective_llm_proxy_mode(settings)
    if proxy_mode == "mock":
        return dependency_status(ok=True, configured=True, mode="mock", required=False)
    try:
        provider = resolve_chat_provider(settings)
        return dependency_status(ok=True, configured=True, mode=provider["provider"], required=True)
    except ServerApiError as exc:
        return dependency_status(ok=False, configured=False, mode=proxy_mode, required=True, error=exc.code)


def vector_dependency_status() -> dict[str, Any]:
    dashscope_configured = bool((settings.dashscope_api_key or "").strip())
    dashvector_configured = bool((settings.dashvector_api_key or "").strip() and (settings.dashvector_endpoint or "").strip())
    return {
        "dashscope": dependency_status(
            ok=dashscope_configured,
            configured=dashscope_configured,
            mode=settings.dashscope_multimodal_embedding_model,
            required=settings.requires_strict_runtime,
        ),
        "dashvector": dependency_status(
            ok=dashvector_configured,
            configured=dashvector_configured,
            mode=settings.dashvector_collection_name,
            required=settings.requires_strict_runtime,
        ),
    }


def runtime_dependency_report() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    try:
        store.mongo.ensure_connection()
        dependencies["mongodb"] = dependency_status(
            ok=True,
            configured=bool(settings.mongodb_uri),
            mode="persistent" if settings.mongodb_uri else "in_memory",
            required=settings.requires_strict_runtime,
        )
    except Exception as exc:
        dependencies["mongodb"] = dependency_status(
            ok=False,
            configured=bool(settings.mongodb_uri),
            mode="persistent" if settings.mongodb_uri else "in_memory",
            required=settings.requires_strict_runtime,
            error=type(exc).__name__,
        )
    try:
        rate_limit_service.ensure_connection()
        dependencies["redis"] = dependency_status(
            ok=True,
            configured=bool(settings.redis_url),
            mode="redis" if settings.redis_url else "in_memory",
            required=settings.requires_strict_runtime,
        )
    except Exception as exc:
        dependencies["redis"] = dependency_status(
            ok=False,
            configured=bool(settings.redis_url),
            mode="redis" if settings.redis_url else "in_memory",
            required=settings.requires_strict_runtime,
            error=type(exc).__name__,
        )
    dependencies["chat_provider"] = provider_dependency_status()
    dependencies.update(vector_dependency_status())
    return dependencies


def update_dependency_health() -> dict[str, Any]:
    dependencies = runtime_dependency_report()
    for dependency_name, status in dependencies.items():
        if isinstance(status, dict) and "ok" in status:
            metrics.set_gauge("server_dependency_health", 1.0 if status["ok"] else 0.0, dependency=dependency_name)
    return dependencies


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    payload = token_service.decode_access_token(bearer_token(authorization))
    user = store.mongo.find_user_by_id(payload["sub"])
    if user is None:
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_INVALID",
            message="The current user no longer exists.",
            error_type="auth_error",
        )
    if user.get("status") != "active":
        raise ServerApiError(
            status_code=403,
            code="USER_SUSPENDED",
            message="The current user is suspended.",
            error_type="auth_error",
        )
    return {"user": user, "token_payload": payload}


__all__ = [
    "RATE_CARDS",
    "Settings",
    "bootstrap_secret",
    "get_current_user",
    "inspect_service",
    "logger",
    "metrics",
    "oauth_service",
    "provider_dependency_status",
    "quota_service",
    "rate_limit_service",
    "request_id",
    "runtime_dependency_report",
    "settings",
    "store",
    "token_service",
    "update_dependency_health",
    "user_service",
    "vector_service",
]
