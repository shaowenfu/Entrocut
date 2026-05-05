from __future__ import annotations

from ...core.config import Settings
from ...core.errors import ServerApiError
from . import registry
from .adapters import gemini, openai_compatible
from .schemas import ChatRequestContext, NormalizedChatResponse


def _read_api_key(settings: Settings, env_name: str) -> str:
    value = ""
    if env_name == "DEEPSEEK_API_KEY":
        value = (settings.deepseek_api_key or "")
    elif env_name == "GOOGLE_API_KEY":
        value = (settings.google_api_key or "")
    value = value.strip()
    if not value:
        raise ServerApiError(status_code=503, code="MODEL_PROVIDER_UNAVAILABLE", message=f"{env_name} is required.", error_type="server_error")
    return value


async def chat(payload: dict, settings: Settings) -> NormalizedChatResponse:
    provider_id = str(payload.get("provider") or "deepseek")
    model = str(payload.get("model") or "deepseek-chat")
    custom_model = str(payload.get("custom_model") or "").strip() or None
    provider = registry.get_provider(settings, provider_id)
    registry.ensure_model(provider, model)
    ctx = ChatRequestContext(
        provider=provider.id,
        model=model,
        effective_model=custom_model or model,
        payload=payload,
        api_key=_read_api_key(settings, provider.api_key_env),
        base_url=provider.base_url or "",
        chat_path=provider.chat_path or "/chat/completions",
    )
    if provider.adapter == "gemini":
        return await gemini.send_chat(ctx)
    if provider.adapter == "openai_compatible":
        return await openai_compatible.send_chat(ctx)
    raise ServerApiError(status_code=500, code="MODEL_PROVIDER_INVALID", message="Unsupported provider adapter.", error_type="server_error")
