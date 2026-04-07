from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from ...core.errors import ServerApiError
from ...shared.time import now_utc
from ...bootstrap.dependencies import effective_llm_proxy_mode, settings, update_dependency_health


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    google_configured = bool(settings.auth_google_client_id and settings.auth_google_client_secret)
    dependencies = update_dependency_health()
    return {
        "status": "ok",
        "service": "server",
        "version": settings.app_version,
        "phase": settings.rewrite_phase,
        "mode": effective_llm_proxy_mode(settings),
        "env": settings.app_env,
        "timestamp": now_utc().isoformat(),
        "dependencies": dependencies,
        "notes": [
            "Phase 1 auth surfaces are enabled.",
            "Google OAuth is configured and ready for local testing."
            if google_configured
            else "Google OAuth is not configured yet. Set AUTH_GOOGLE_CLIENT_ID and AUTH_GOOGLE_CLIENT_SECRET.",
            "Chat proxy runs in mock mode."
            if effective_llm_proxy_mode(settings) == "mock"
            else "Chat proxy forwards requests to the configured upstream provider.",
        ],
    }


@router.get("/livez")
def livez() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "server",
        "env": settings.app_env,
        "timestamp": now_utc().isoformat(),
    }


@router.get("/readyz")
def readyz() -> JSONResponse:
    dependencies = update_dependency_health()
    failed_dependencies = [
        dependency_name
        for dependency_name, status in dependencies.items()
        if isinstance(status, dict) and status.get("required") and not status.get("ok")
    ]
    status_code = 200 if not failed_dependencies else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if status_code == 200 else "not_ready",
            "service": "server",
            "env": settings.app_env,
            "dependencies": dependencies,
        },
    )


@router.get("/metrics")
def metrics_endpoint() -> PlainTextResponse:
    from ...bootstrap.dependencies import metrics

    if not settings.observability_enable_metrics:
        raise ServerApiError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="Metrics endpoint is disabled.",
            error_type="invalid_request_error",
        )
    update_dependency_health()
    return PlainTextResponse(metrics.render_prometheus(), media_type="text/plain; version=0.0.4")
