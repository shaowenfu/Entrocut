from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...bootstrap.dependencies import inspect_service, provider_dependency_status, settings
from ...schemas.runtime import RuntimeCapabilitiesResponse, RuntimeModelsResponse
from ...services.models.registry import _providers


router = APIRouter(tags=["runtime"])


def _runtime_models() -> RuntimeModelsResponse:
    providers = []
    warnings: list[str] = []
    for p in _providers(settings):
        api_key = (settings.deepseek_api_key if p.id == "deepseek" else settings.google_api_key) or ""
        providers.append({
            "id": p.id,
            "label": p.label,
            "available": bool(api_key.strip()),
            "models": [
                {"id": m.id, "label": m.label, "available": bool(api_key.strip()), "supports_custom_model": m.supports_custom_model}
                for m in p.models
            ],
        })
    return RuntimeModelsResponse(default_provider="deepseek", default_model="deepseek-chat", providers=providers, warnings=warnings)


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
                "provider": models.default_provider,
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
            "quota_free_total_tokens": settings.quota_free_total_tokens,
            "rate_limit_requests_per_minute": settings.rate_limit_requests_per_minute,
            "rate_limit_tokens_per_minute": settings.rate_limit_tokens_per_minute,
            "llm_upstream_configured": bool(settings.deepseek_api_key or settings.google_api_key),
        },
    }
