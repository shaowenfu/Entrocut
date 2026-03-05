from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Server Shell",
    version="0.1.0",
    description="Cloud Orchestration Shell（云端编排壳层）"
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


class ChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    session_id: str | None = Field(default=None, description="Session ID（会话标识）")
    user_id: str | None = Field(default=None, description="User ID（用户标识）")
    message: str = Field(..., description="User prompt（用户输入）")
    context: dict[str, Any] | None = Field(default=None, description="Context payload（上下文）")
    current_project: dict[str, Any] | None = Field(
        default=None, description="Current project contract（当前项目契约）"
    )


class ChatAcceptedResponse(BaseModel):
    ok: bool = True
    status: str = "accepted"
    request_id: str
    project_id: str
    queued_at: str


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
    return {"status": "ok", "service": "server", "version": "0.1.0"}


@app.post("/api/v1/chat", response_model=ChatAcceptedResponse)
def chat(request: ChatRequest) -> ChatAcceptedResponse:
    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SERVER_CHAT_CONTEXT_INVALID",
                "message": "message is required.",
            },
        )

    return ChatAcceptedResponse(
        request_id=f"req_{uuid4().hex[:10]}",
        project_id=request.project_id,
        queued_at=datetime.now(tz=UTC).isoformat(),
    )
