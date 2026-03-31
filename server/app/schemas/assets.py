from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VectorizeDocContent(BaseModel):
    image_base64: str = Field(..., min_length=16)


class VectorizeDocFields(BaseModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    asset_id: str = Field(..., min_length=1, max_length=128)
    project_id: str = Field(..., min_length=1, max_length=128)
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
    collection_name: str = "entrocut_assets"
    partition: str = "default"
    model: str = "qwen3-vl-embedding"
    dimension: int = 1024
    docs: list[VectorizeDoc] = Field(..., min_length=1)


class VectorizeResponse(BaseModel):
    collection_name: str
    partition: str
    model: str
    dimension: int
    inserted_count: int
    results: list[VectorizeResultItem]
    usage: VectorizeUsage | None = None


class AssetRetrievalRequest(BaseModel):
    collection_name: str = "entrocut_assets"
    partition: str = "default"
    model: str = "qwen3-vl-embedding"
    dimension: int = 1024
    query_text: str = Field(..., min_length=1, max_length=2000)
    topk: int = Field(default=8, ge=1, le=100)
    filter: str | None = Field(default=None, alias="filter")
    include_vector: bool = False
    output_fields: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


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
    collection_name: str
    partition: str
    query: RetrievalQuery
    matches: list[RetrievalMatch]
    usage: dict[str, int]
