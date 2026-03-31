from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssetReference(BaseModel):
    type: Literal["image_url", "video_url", "text"]
    content: str = Field(..., description="图片 URL 或文本内容")
    mime_type: str | None = Field(default=None, description="可选的 MIME 类型提示")


class AssetVector(BaseModel):
    asset_id: str
    vector: list[float]
    dimension: int
