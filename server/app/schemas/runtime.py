from __future__ import annotations

from pydantic import BaseModel


class RuntimeCapabilityItem(BaseModel):
    available: bool
    provider: str | None = None
    mode: str | None = None
    reason: str | None = None


class RuntimeCapabilitiesResponse(BaseModel):
    service: str
    version: str
    phase: str
    mode: str
    retained_surfaces: list[str]
    capabilities: dict[str, RuntimeCapabilityItem] | None = None


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
