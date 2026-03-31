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
