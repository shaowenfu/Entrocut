from __future__ import annotations

from fastapi import APIRouter

from ...bootstrap.dependencies import settings
from ...schemas.runtime import RuntimeModelsResponse
from ...services.models.registry import provider_available, providers as model_providers


router = APIRouter(tags=["runtime"])


def _runtime_models() -> RuntimeModelsResponse:
    response_providers = []
    warnings: list[str] = []
    default_provider = settings.llm_default_provider.strip() or "google_gemini"
    default_model = settings.llm_default_model.strip() or "gemini-3.1-flash-lite-preview"
    first_available_provider: str | None = None
    first_available_model: str | None = None
    configured_default_available = False
    for provider in model_providers(settings):
        available = provider_available(settings, provider)
        if not available:
            warnings.append(f"{provider.id}_api_key_missing")
        elif first_available_provider is None and provider.models:
            first_available_provider = provider.id
            first_available_model = provider.models[0].id
        if provider.id == default_provider and available and any(model.id == default_model for model in provider.models):
            configured_default_available = True
        response_providers.append(
            {
                "id": provider.id,
                "label": provider.label,
                "available": available,
                "models": [
                    {
                        "id": model.id,
                        "label": model.label,
                        "available": available,
                        "supports_custom_model": model.supports_custom_model,
                    }
                    for model in provider.models
                ],
            }
        )
    if not configured_default_available and first_available_provider and first_available_model:
        default_provider = first_available_provider
        default_model = first_available_model
    return RuntimeModelsResponse(
        default_provider=default_provider,
        default_model=default_model,
        providers=response_providers,
        warnings=warnings,
    )


@router.get("/api/v1/runtime/models", response_model=RuntimeModelsResponse)
def runtime_models() -> RuntimeModelsResponse:
    return _runtime_models()
