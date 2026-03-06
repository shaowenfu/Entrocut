from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Server Shell",
    version="0.2.0",
    description="Cloud Orchestration Shell（云端编排壳层）",
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


class ClipPayload(BaseModel):
    clip_id: str
    asset_id: str
    start_ms: int
    end_ms: int
    score: float
    description: str


class IndexUpsertRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    clips: list[ClipPayload] = Field(default_factory=list, description="Clip payload（片段负载）")


class IndexUpsertResponse(BaseModel):
    ok: bool = True
    request_id: str
    indexed: int
    failed: int


class ChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    session_id: str | None = Field(default=None, description="Session ID（会话标识）")
    user_id: str | None = Field(default=None, description="User ID（用户标识）")
    message: str = Field(..., description="User prompt（用户输入）")
    context: dict[str, Any] | None = Field(default=None, description="Context payload（上下文）")
    current_project: dict[str, Any] | None = Field(
        default=None, description="Current project contract（当前项目契约）"
    )


class StoryboardScene(BaseModel):
    id: str
    title: str
    duration: str
    intent: str


class ChatDecisionResponse(BaseModel):
    decision_type: Literal["UPDATE_PROJECT_CONTRACT", "APPLY_PATCH_ONLY", "ASK_USER_CLARIFICATION"]
    project_id: str
    reasoning_summary: str
    ops: list[str]
    storyboard_scenes: list[StoryboardScene] = Field(default_factory=list)
    meta: dict[str, Any]


_INDEX_STORE: dict[str, set[str]] = {}
_INDEX_LOCK = Lock()


def _chat_error(code: str, message: str, status_code: int = 400) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def _scene(scene_id: str, title: str, duration: str, intent: str) -> StoryboardScene:
    return StoryboardScene(id=scene_id, title=title, duration=duration, intent=intent)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "server", "version": "0.2.0"}


@app.post("/api/v1/index/upsert-clips", response_model=IndexUpsertResponse)
def index_upsert(request: IndexUpsertRequest) -> IndexUpsertResponse:
    if not request.project_id.strip():
        _chat_error("SERVER_VECTOR_UPSERT_FAILED", "project_id is required.")

    with _INDEX_LOCK:
        indexed_set = _INDEX_STORE.setdefault(request.project_id, set())
        for clip in request.clips:
            indexed_set.add(clip.clip_id)
        indexed = len(request.clips)

    return IndexUpsertResponse(
        request_id=f"req_{uuid4().hex[:10]}",
        indexed=indexed,
        failed=0,
    )


@app.post("/api/v1/chat", response_model=ChatDecisionResponse)
def chat(request: ChatRequest) -> ChatDecisionResponse:
    message = request.message.strip()
    if not message:
        _chat_error("SERVER_CHAT_CONTEXT_INVALID", "message is required.")

    has_media = bool((request.context or {}).get("has_media"))
    clip_count = int((request.context or {}).get("clip_count") or 0)
    request_id = f"req_{uuid4().hex[:10]}"
    latency_ms = 1200 if has_media else 600

    if not has_media:
        return ChatDecisionResponse(
            decision_type="ASK_USER_CLARIFICATION",
            project_id=request.project_id,
            reasoning_summary="当前项目没有可用素材，请先上传视频再继续剪辑。",
            ops=[
                "Open Assets panel",
                "Upload local videos",
                "Retry the same prompt",
            ],
            storyboard_scenes=[],
            meta={
                "request_id": request_id,
                "latency_ms": latency_ms,
            },
        )

    lower = message.lower()
    if "slow" in lower or "慢" in message:
        scenes = [
            _scene("scene_1", "Calm Establishing", "6s", "Slow pan for atmosphere"),
            _scene("scene_2", "Subject Focus", "8s", "Longer hold to keep pace calm"),
            _scene("scene_3", "Breathing Detail", "5s", "Insert detail shots for rhythm"),
        ]
    else:
        scenes = [
            _scene("scene_1", "Fast Establishing", "4s", "Quick establish with movement"),
            _scene("scene_2", "Hero Reveal", "6s", "Cut to subject with strong visual anchor"),
            _scene("scene_3", "Momentum Push", "5s", "Increase cadence before transition"),
        ]

    return ChatDecisionResponse(
        decision_type="UPDATE_PROJECT_CONTRACT",
        project_id=request.project_id,
        reasoning_summary="我已根据当前素材和你的指令生成一版可继续迭代的分镜方案。",
        ops=[
            f"Used indexed clips: {max(clip_count, len(scenes))}",
            "Updated storyboard proposal",
        ],
        storyboard_scenes=scenes,
        meta={
            "request_id": request_id,
            "latency_ms": latency_ms,
            "queued_at": datetime.now(tz=UTC).isoformat(),
        },
    )
