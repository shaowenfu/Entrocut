from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from uuid import uuid4

CoreEventName = Literal[
    "session.ready",
    "notification",
    "launchpad.project.initialized",
    "media.processing.progress",
    "media.processing.completed",
    "workspace.chat.received",
    "workspace.chat.ready",
    "workspace.patch.ready",
]

ProjectWorkflowState = Literal[
    "prompt_input_required",
    "awaiting_media",
    "media_ready",
    "media_processing",
    "chat_thinking",
    "ready",
    "rendering",
    "failed",
]


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class CoreEventEnvelope(BaseModel):
    event: CoreEventName
    project_id: str
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    sequence: int = 0
    session_id: str | None = None
    request_id: str | None = None
    ts: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)


class CoreSessionReadyPayload(BaseModel):
    project_id: str
    status: str = "connected"
    connection_id: str
    authenticated_user_id: str
    last_sequence: int = 0
    replayed_count: int = 0
    active_task_type: str | None = None
    workflow_state: ProjectWorkflowState = "ready"
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "launchpad.workflow",
            "workspace.workflow",
            "media.progress",
            "chat.notifications",
            "event.sequence",
            "session.resume",
        ]
    )


class NotificationPayload(BaseModel):
    level: Literal["info", "warning", "error"] = "info"
    message: str


class MediaProgressPayload(BaseModel):
    stage: Literal["scan", "segment", "extract_frames", "embed", "index", "render"]
    progress: float = Field(ge=0.0, le=1.0)
    message: str


class IngestProgressPayload(BaseModel):
    """详细的ingest进度信息"""

    stage: Literal["scan", "segment", "extract_frames", "embed", "index", "render"]
    stage_progress: float = Field(ge=0.0, le=1.0)  # 当前阶段内进度
    overall_progress: float = Field(ge=0.0, le=1.0)  # 总体进度
    current_asset: str | None = None  # 当前处理的资产名
    processed_count: int = 0  # 已处理数量
    total_count: int = 0  # 总数量
    message: str

    # 阶段状态跟踪
    stage_stats: dict[str, Any] = Field(default_factory=dict)
    # 示例: {"scan": {"status": "completed", "count": 10}, ...}


class WorkspacePatchPayload(BaseModel):
    turn_id: str | None = None
    decision_type: str = "UPDATE_PROJECT_CONTRACT"
    workflow_state: ProjectWorkflowState = "ready"
    reasoning_summary: str
    ops: list[dict[str, Any]] = Field(default_factory=list)
