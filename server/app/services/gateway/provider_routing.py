from __future__ import annotations

from ...core.config import Settings
from ...core.errors import ServerApiError


def effective_llm_proxy_mode(settings: Settings) -> str:
    return settings.llm_proxy_mode.strip().lower()


def resolve_upstream_model(settings: Settings, model: str) -> str:
    if settings.llm_upstream_default_model:
        return settings.llm_upstream_default_model.strip()
    return model.strip() or settings.llm_default_model


def resolve_chat_provider(settings: Settings) -> dict[str, str]:
    proxy_mode = effective_llm_proxy_mode(settings)
    if proxy_mode == "google_gemini":
        api_key = (settings.google_api_key or "").strip()
        if not api_key:
            raise ServerApiError(
                status_code=503,
                code="MODEL_PROVIDER_UNAVAILABLE",
                message="GOOGLE_API_KEY is required when llm_proxy_mode=google_gemini.",
                error_type="server_error",
            )
        return {
            "provider": "google_gemini",
            "base_url": settings.llm_gemini_base_url.rstrip("/"),
            "chat_path": settings.llm_gemini_chat_path,
            "api_key": api_key,
        }
    if proxy_mode == "upstream":
        base_url = (settings.llm_upstream_base_url or "").strip()
        api_key = (settings.llm_upstream_api_key or "").strip()
        if not base_url or not api_key:
            raise ServerApiError(
                status_code=503,
                code="MODEL_PROVIDER_UNAVAILABLE",
                message="No upstream provider is configured for server chat proxy.",
                error_type="server_error",
            )
        return {
            "provider": "openai_compatible_upstream",
            "base_url": base_url.rstrip("/"),
            "chat_path": settings.llm_upstream_chat_path,
            "api_key": api_key,
        }
    raise ServerApiError(
        status_code=503,
        code="MODEL_PROVIDER_UNAVAILABLE",
        message="Chat proxy provider is not configured.",
        error_type="server_error",
    )
