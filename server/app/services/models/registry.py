from __future__ import annotations

from ...core.config import Settings
from ...core.errors import ServerApiError
from .schemas import ModelDefinition, ProviderDefinition


def _providers(settings: Settings) -> tuple[ProviderDefinition, ...]:
    return (
        ProviderDefinition(
            id="deepseek",
            label="DeepSeek",
            adapter="openai_compatible",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            chat_path="/chat/completions",
            models=(
                ModelDefinition(id="deepseek-chat", label="DeepSeek Chat"),
                ModelDefinition(id="deepseek-reasoner", label="DeepSeek Reasoner"),
            ),
        ),
        ProviderDefinition(
            id="google_gemini",
            label="Google Gemini",
            adapter="gemini",
            api_key_env="GOOGLE_API_KEY",
            base_url=settings.llm_gemini_base_url.rstrip("/"),
            chat_path=settings.llm_gemini_chat_path,
            models=(
                ModelDefinition(id="gemini-2.5-flash", label="Gemini 2.5 Flash"),
                ModelDefinition(id="gemini-2.5-pro", label="Gemini 2.5 Pro"),
            ),
        ),
    )


def get_provider(settings: Settings, provider_id: str) -> ProviderDefinition:
    provider = next((p for p in _providers(settings) if p.id == provider_id), None)
    if provider is None:
        raise ServerApiError(status_code=422, code="MODEL_PROVIDER_NOT_SUPPORTED", message=f"Unsupported provider: {provider_id}", error_type="invalid_request_error")
    return provider


def ensure_model(provider: ProviderDefinition, model_id: str) -> None:
    if any(model.id == model_id for model in provider.models):
        return
    raise ServerApiError(status_code=422, code="MODEL_NOT_SUPPORTED", message=f"Unsupported model '{model_id}' for provider '{provider.id}'.", error_type="invalid_request_error")

