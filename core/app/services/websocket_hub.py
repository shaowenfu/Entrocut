from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket

from app.schemas.events import CoreEventEnvelope


class ProjectWebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[project_id].add(websocket)

    async def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(project_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(project_id, None)

    async def broadcast(self, event: CoreEventEnvelope) -> None:
        async with self._lock:
            sockets = list(self._connections.get(event.project_id, set()))

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(event.model_dump())
            except Exception:
                stale.append(websocket)

        if not stale:
            return

        async with self._lock:
            active = self._connections.get(event.project_id)
            if not active:
                return
            for websocket in stale:
                active.discard(websocket)
            if not active:
                self._connections.pop(event.project_id, None)
