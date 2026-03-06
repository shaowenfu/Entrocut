from __future__ import annotations

from app.schemas.events import CoreEventEnvelope, MediaProgressPayload, NotificationPayload
from app.services.websocket_hub import ProjectWebSocketHub


class LaunchpadWorkflowShell:
    def __init__(self, hub: ProjectWebSocketHub) -> None:
        self._hub = hub

    async def notify_project_initialized(self, *, project_id: str, title: str, request_id: str | None = None) -> None:
        await self._hub.broadcast(
            CoreEventEnvelope(
                event="launchpad.project.initialized",
                project_id=project_id,
                request_id=request_id,
                payload={"title": title},
            )
        )

    async def notify_media_progress(
        self,
        *,
        project_id: str,
        stage: str,
        progress: float,
        message: str,
        request_id: str | None = None,
    ) -> None:
        payload = MediaProgressPayload(stage=stage, progress=progress, message=message).model_dump()
        await self._hub.broadcast(
            CoreEventEnvelope(
                event="media.processing.progress",
                project_id=project_id,
                request_id=request_id,
                payload=payload,
            )
        )

    async def notify_media_completed(self, *, project_id: str, message: str, request_id: str | None = None) -> None:
        payload = NotificationPayload(level="info", message=message).model_dump()
        await self._hub.broadcast(
            CoreEventEnvelope(
                event="media.processing.completed",
                project_id=project_id,
                request_id=request_id,
                payload=payload,
            )
        )
