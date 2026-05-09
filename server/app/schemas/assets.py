from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VectorizeDocContent(BaseModel):
    image_base64: str = Field(..., min_length=16)


class VectorizeDocFields(BaseModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    asset_id: str = Field(..., min_length=1, max_length=128)
    project_id: str = Field(..., min_length=1, max_length=128)
    asset_state: str = Field(default="active", min_length=1, max_length=32)
    asset_active: bool = True
    source_start_ms: int = Field(..., ge=0)
    source_end_ms: int = Field(..., gt=0)
    frame_count: int | None = Field(default=None, ge=1)


class VectorizeDoc(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    content: VectorizeDocContent
    fields: VectorizeDocFields


class VectorizeResultItem(BaseModel):
    id: str
    status: str = "inserted"


class VectorizeUsage(BaseModel):
    embedding_doc_count: int
    dashvector_write_units: int | None = None


class VectorizeRequest(BaseModel):
    docs: list[VectorizeDoc] = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class VectorizeResponse(BaseModel):
    inserted_count: int
    results: list[VectorizeResultItem]
    usage: VectorizeUsage | None = None


class AssetRetrievalRequest(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=2000)
    filter: str | None = Field(default=None, alias="filter")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class RetrievalMatch(BaseModel):
    id: str
    score: float
    vector: list[float] | None = None
    fields: dict[str, Any]


class RetrievalQuery(BaseModel):
    query_text: str
    topk: int
    filter: str | None = Field(default=None, alias="filter")

    model_config = {"populate_by_name": True}


class AssetRetrievalResponse(BaseModel):
    query: RetrievalQuery
    matches: list[RetrievalMatch]
    usage: dict[str, int]


class AssetVectorIndexStateRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=128)
    asset_id: str = Field(..., min_length=1, max_length=128)
    active: bool
    clip_ids: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class AssetVectorIndexStateResponse(BaseModel):
    project_id: str
    asset_id: str
    active: bool
    updated_count: int
    skipped_count: int = 0
