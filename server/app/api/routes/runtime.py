from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...bootstrap.dependencies import inspect_service, provider_dependency_status, settings
from ...schemas.runtime import RuntimeCapabilitiesResponse
from ...services.gateway.provider_routing import effective_llm_proxy_mode


router = APIRouter(tags=["runtime"])


@router.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    return RuntimeCapabilitiesResponse(
        service="server",
        version=settings.app_version,
        phase=settings.rewrite_phase,
        mode="auth_phase1",
        retained_surfaces=[
            "health",
            "livez",
            "readyz",
            "metrics",
            "runtime_capabilities",
            "request_id_middleware",
            "auth_login_sessions",
            "auth_oauth_google",
            "auth_test_bootstrap",
            "auth_refresh",
            "auth_logout",
            "me",
            "user_profile",
            "user_usage",
            "chat_completions_proxy",
            "assets_vectorize",
            "assets_retrieval",
            "tools_inspect",
        ],
        capabilities={
            "planner_chat": {"available": True, "provider": provider_dependency_status().get("mode")},
            "multimodal_embedding": {
                "available": bool((settings.dashscope_api_key or "").strip()),
                "provider": settings.dashscope_multimodal_embedding_model,
            },
            "vector_retrieval": {
                "available": bool((settings.dashvector_api_key or "").strip() and (settings.dashvector_endpoint or "").strip()),
                "provider": "dashvector",
            },
            "inspect_image": {
                "available": bool((settings.google_api_key or "").strip()),
                "provider": inspect_service.peek_provider_name(),
                "mode": "ordered_keyframes",
            },
            "inspect_video": {
                "available": False,
                "reason": "not_enabled_in_phase_1",
            },
        },
    )


@router.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "server",
        "phase": settings.rewrite_phase,
        "mode": "auth_phase1",
        "message": "EntroCut server now provides auth surfaces and an authenticated OpenAI-compatible chat proxy.",
        "env": {
            "mongodb_configured": bool(settings.mongodb_uri),
            "redis_configured": bool(settings.redis_url),
            "google_oauth_configured": bool(
                settings.auth_google_client_id and settings.auth_google_client_secret
            ),
            "auth_jwt_algorithm": settings.auth_jwt_algorithm,
            "llm_proxy_mode": settings.llm_proxy_mode,
            "quota_free_total_tokens": settings.quota_free_total_tokens,
            "rate_limit_requests_per_minute": settings.rate_limit_requests_per_minute,
            "rate_limit_tokens_per_minute": settings.rate_limit_tokens_per_minute,
            "llm_upstream_configured": bool(
                (settings.llm_upstream_base_url and settings.llm_upstream_api_key)
                or (effective_llm_proxy_mode(settings) == "google_gemini" and settings.google_api_key)
            ),
        },
    }
