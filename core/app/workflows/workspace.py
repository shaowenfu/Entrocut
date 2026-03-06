from __future__ import annotations

from typing import Any

from app.schemas.events import CoreEventEnvelope, NotificationPayload, WorkspacePatchPayload
from app.services.websocket_hub import ProjectWebSocketHub


class WorkspaceWorkflowShell:
    def __init__(self, hub: ProjectWebSocketHub) -> None:
        self._hub = hub

    async def notify_chat_received(self, *, project_id: str, message: str, request_id: str | None = None) -> None:
        await self._hub.broadcast(
            CoreEventEnvelope(
                event="workspace.chat.received",
                project_id=project_id,
                request_id=request_id,
                payload={"message": message},
            )
        )

    async def notify_chat_ready(self, *, project_id: str, summary: str, request_id: str | None = None) -> None:
        payload = NotificationPayload(level="info", message=summary).model_dump()
        await self._hub.broadcast(
            CoreEventEnvelope(
                event="workspace.chat.ready",
                project_id=project_id,
                request_id=request_id,
                payload=payload,
            )
        )

    async def notify_patch_ready(
        self,
        *,
        project_id: str,
        reasoning_summary: str,
        ops: list[dict[str, Any]],
        request_id: str | None = None,
    ) -> None:
        payload = WorkspacePatchPayload(reasoning_summary=reasoning_summary, ops=ops).model_dump()
        await self._hub.broadcast(
            CoreEventEnvelope(
                event="workspace.patch.ready",
                project_id=project_id,
                request_id=request_id,
                payload=payload,
            )
        )
