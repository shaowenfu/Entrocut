from __future__ import annotations

from ...core.config import Settings
from ...core.errors import ServerApiError
from .schemas import ModelDefinition, ProviderDefinition


def providers(settings: Settings) -> tuple[ProviderDefinition, ...]:
    gemini_base_url = settings.llm_gemini_base_url.rstrip("/")
    if gemini_base_url.endswith("/openai"):
        gemini_base_url = gemini_base_url.removesuffix("/openai")
    return (
        ProviderDefinition(
            id="deepseek",
            label="DeepSeek",
            adapter="openai_compatible",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            chat_path="/chat/completions",
            models=(
                ModelDefinition(id="deepseek-v4-flash", label="DeepSeek V4 Flash"),
                ModelDefinition(id="deepseek-v4-pro", label="DeepSeek V4 Pro"),
            ),
        ),
        ProviderDefinition(
            id="google_gemini",
            label="Google Gemini",
            adapter="gemini",
            api_key_env="GOOGLE_API_KEY",
            base_url=gemini_base_url,
            chat_path=None,
            models=(
                ModelDefinition(id="gemini-2.5-flash", label="Gemini 2.5 Flash"),
                ModelDefinition(id="gemini-2.5-pro", label="Gemini 2.5 Pro"),
            ),
        ),
    )


def get_provider(settings: Settings, provider_id: str) -> ProviderDefinition:
    provider = next((p for p in providers(settings) if p.id == provider_id), None)
    if provider is None:
        raise ServerApiError(
            status_code=422,
            code="MODEL_PROVIDER_NOT_SUPPORTED",
            message=f"Unsupported provider: {provider_id}",
            error_type="invalid_request_error",
        )
    return provider


def ensure_model(provider: ProviderDefinition, model_id: str) -> None:
    if any(model.id == model_id for model in provider.models):
        return
    raise ServerApiError(
        status_code=422,
        code="MODEL_NOT_SUPPORTED",
        message=f"Unsupported model '{model_id}' for provider '{provider.id}'.",
        error_type="invalid_request_error",
    )


def provider_api_key(settings: Settings, provider: ProviderDefinition) -> str:
    if provider.api_key_env == "DEEPSEEK_API_KEY":
        return (settings.deepseek_api_key or "").strip()
    if provider.api_key_env == "GOOGLE_API_KEY":
        return (settings.google_api_key or "").strip()
    return ""


def provider_available(settings: Settings, provider: ProviderDefinition) -> bool:
    return bool(provider_api_key(settings, provider))
