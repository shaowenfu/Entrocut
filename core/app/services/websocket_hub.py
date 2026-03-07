from __future__ import annotations

import asyncio
from collections import defaultdict
from collections import deque
from uuid import uuid4

from fastapi import WebSocket

from app.schemas.events import CoreEventEnvelope


class ProjectWebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._sequence_by_project: dict[str, int] = defaultdict(int)
        self._history_by_project: dict[str, deque[CoreEventEnvelope]] = defaultdict(lambda: deque(maxlen=128))
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, websocket: WebSocket) -> str:
        await websocket.accept()
        async with self._lock:
            self._connections[project_id].add(websocket)
        return f"ws_{uuid4().hex[:12]}"

    async def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(project_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(project_id, None)

    async def current_sequence(self, project_id: str) -> int:
        async with self._lock:
            return self._sequence_by_project.get(project_id, 0)

    async def replay(self, project_id: str, websocket: WebSocket, *, after_sequence: int) -> int:
        async with self._lock:
            history = list(self._history_by_project.get(project_id, ()))
        replayed = 0
        for event in history:
            if event.sequence <= after_sequence:
                continue
            await websocket.send_json(event.model_dump())
            replayed += 1
        return replayed

    async def broadcast(self, event: CoreEventEnvelope) -> int:
        async with self._lock:
            self._sequence_by_project[event.project_id] = self._sequence_by_project.get(event.project_id, 0) + 1
            event.sequence = self._sequence_by_project[event.project_id]
            self._history_by_project[event.project_id].append(event)
            sockets = list(self._connections.get(event.project_id, set()))

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(event.model_dump())
            except Exception:
                stale.append(websocket)

        if not stale:
            return event.sequence

        async with self._lock:
            active = self._connections.get(event.project_id)
            if not active:
                return event.sequence
            for websocket in stale:
                active.discard(websocket)
            if not active:
                self._connections.pop(event.project_id, None)
        return event.sequence
