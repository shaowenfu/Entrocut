from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Core Shell",
    version="0.1.0",
    description="Local Service Shell（本地服务壳层）"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    video_path: str = Field(..., description="Local video path（本地视频路径）")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Semantic query（语义查询）")


class RenderRequest(BaseModel):
    project: dict[str, Any] = Field(..., description="Editable Timeline JSON（可编辑时间线）")


def _not_implemented(feature_name: str) -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "code": "NOT_IMPLEMENTED",
            "message": f"{feature_name} is not implemented in baseline."
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "core", "version": "0.1.0"}


@app.post("/api/v1/ingest")
def ingest(_: IngestRequest) -> None:
    _not_implemented("Ingestion")


@app.post("/api/v1/search")
def search(_: SearchRequest) -> None:
    _not_implemented("Semantic Search")


@app.post("/api/v1/render")
def render(_: RenderRequest) -> None:
    _not_implemented("Render")
