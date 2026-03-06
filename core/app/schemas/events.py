from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

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


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class CoreEventEnvelope(BaseModel):
    event: CoreEventName
    project_id: str
    session_id: str | None = None
    request_id: str | None = None
    ts: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)


class CoreSessionReadyPayload(BaseModel):
    project_id: str
    status: str = "connected"
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "launchpad.workflow",
            "workspace.workflow",
            "media.progress",
            "chat.notifications",
        ]
    )


class NotificationPayload(BaseModel):
    level: Literal["info", "warning", "error"] = "info"
    message: str


class MediaProgressPayload(BaseModel):
    stage: Literal["scan", "segment", "extract_frames", "embed", "index", "render"]
    progress: float = Field(ge=0.0, le=1.0)
    message: str


class WorkspacePatchPayload(BaseModel):
    reasoning_summary: str
    ops: list[dict[str, Any]] = Field(default_factory=list)

