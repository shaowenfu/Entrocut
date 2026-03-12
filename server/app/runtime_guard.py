from __future__ import annotations

from .config import Settings
from .errors import ServerApiError


def validate_runtime_settings(settings: Settings) -> None:
    if not settings.requires_strict_runtime:
        return

    if settings.auth_jwt_secret == "entrocut-dev-secret-change-me":
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="AUTH_JWT_SECRET must be replaced in staging/production.",
            error_type="server_error",
        )

    if settings.auth_dev_fallback_enabled:
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="AUTH_DEV_FALLBACK_ENABLED must be false in staging/production.",
            error_type="server_error",
        )

    if settings.staging_test_bootstrap_enabled and not (settings.staging_test_bootstrap_secret or "").strip():
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="STAGING_TEST_BOOTSTRAP_SECRET is required when staging bootstrap is enabled.",
            error_type="server_error",
        )

    if not settings.mongodb_uri or not settings.mongodb_uri.strip():
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="MONGODB_URI is required in staging/production.",
            error_type="server_error",
        )

    if not settings.redis_url or not settings.redis_url.strip():
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="REDIS_URL is required in staging/production.",
            error_type="server_error",
        )

    if settings.allow_inmemory_mongo_fallback:
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="ALLOW_INMEMORY_MONGO_FALLBACK must be false in staging/production.",
            error_type="server_error",
        )

    if settings.allow_inmemory_redis_fallback:
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="ALLOW_INMEMORY_REDIS_FALLBACK must be false in staging/production.",
            error_type="server_error",
        )

    normalized_origins = [origin.lower() for origin in settings.allow_origins]
    if not normalized_origins:
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="CORS_ALLOW_ORIGINS cannot be empty in staging/production.",
            error_type="server_error",
        )
    contains_localhost_origin = any(
        "localhost" in origin or "127.0.0.1" in origin for origin in normalized_origins
    )
    if settings.is_production and contains_localhost_origin:
        raise ServerApiError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="CORS_ALLOW_ORIGINS cannot contain localhost entries in production.",
            error_type="server_error",
        )
