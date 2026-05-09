from __future__ import annotations

from pydantic import BaseModel, Field


class InspectRequest(BaseModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    prompt: str = Field(..., min_length=1, max_length=2000)
    image_base64: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class InspectResponse(BaseModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=4000)
    uncertainty: str | None = Field(default=None, max_length=1000)
    model: str | None = Field(default=None, min_length=1, max_length=128)
