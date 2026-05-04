from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...bootstrap.dependencies import inspect_service, provider_dependency_status, settings
from ...schemas.runtime import RuntimeCapabilitiesResponse, RuntimeModelItem, RuntimeModelsResponse
from ...services.gateway.provider_routing import effective_llm_proxy_mode


router = APIRouter(tags=["runtime"])


def _runtime_models() -> RuntimeModelsResponse:
    provider_status = provider_dependency_status()
    provider_mode = effective_llm_proxy_mode(settings)
    provider_name = str(provider_status.get("mode") or provider_mode)
    upstream_model = None
    warnings: list[str] = []
    reason = None
    available = bool(provider_status.get("ok"))

    if provider_mode == "google_gemini":
        upstream_model = settings.llm_gemini_default_model.strip() or "gemini-2.5-flash"
    elif provider_mode == "upstream":
        upstream_model = (
            settings.llm_upstream_default_model.strip()
            if settings.llm_upstream_default_model
            else settings.llm_default_model
        )
    elif provider_mode == "mock":
        upstream_model = "mock-planner-json"
        warnings.append("planner_chat_is_using_mock_json_provider")
    else:
        available = False
        reason = "provider_not_configured"

    if not available and reason is None:
        reason = str(provider_status.get("error") or "provider_unavailable")

    return RuntimeModelsResponse(
        default_model=settings.llm_default_model,
        provider_mode=provider_mode,
        platform_models=[
            RuntimeModelItem(
                id=settings.llm_default_model,
                label="Entro Reasoning",
                available=available,
                route=provider_name,
                upstream_model=upstream_model,
                provider=provider_name,
                reason=reason,
            )
        ],
        warnings=warnings,
    )


@router.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    models = _runtime_models()
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
            "platform_models": {
                "available": any(model.available for model in models.platform_models),
                "provider": models.provider_mode,
                "mode": models.default_model,
                "reason": ",".join(models.warnings) if models.warnings else None,
            },
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


@router.get("/api/v1/runtime/models", response_model=RuntimeModelsResponse)
def runtime_models() -> RuntimeModelsResponse:
    return _runtime_models()


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
