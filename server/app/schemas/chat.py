from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str = Field(..., min_length=1)
    content: Any

    model_config = ConfigDict(extra="allow")


class ChatCompletionsRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    custom_model: str | None = None
    provider: str | None = None
    stream: bool = False
    stream_options: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")
