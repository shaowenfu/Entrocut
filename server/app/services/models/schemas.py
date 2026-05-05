from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelDefinition:
    id: str
    label: str
    supports_custom_model: bool = True


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    label: str
    adapter: str
    api_key_env: str
    base_url: str | None
    chat_path: str | None
    models: tuple[ModelDefinition, ...]


@dataclass(frozen=True)
class ChatRequestContext:
    provider: str
    model: str
    effective_model: str
    payload: dict[str, Any]
    api_key: str
    base_url: str
    chat_path: str


@dataclass(frozen=True)
class NormalizedChatResponse:
    body: dict[str, Any]
    provider_model: str | None

