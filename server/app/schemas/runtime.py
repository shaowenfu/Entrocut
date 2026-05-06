from __future__ import annotations

from pydantic import BaseModel


class RuntimeModelItem(BaseModel):
    id: str
    label: str
    available: bool
    supports_custom_model: bool = True


class RuntimeProviderItem(BaseModel):
    id: str
    label: str
    available: bool
    models: list[RuntimeModelItem]


class RuntimeModelsResponse(BaseModel):
    default_model: str
    default_provider: str
    providers: list[RuntimeProviderItem]
    warnings: list[str] = []
