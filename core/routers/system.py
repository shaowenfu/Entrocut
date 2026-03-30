from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import APP_VERSION, CORE_MODE, REWRITE_PHASE, SERVER_BASE_URL
from helpers import _now_iso
from schemas import CoreApiError, RuntimeCapabilitiesResponse
from store import store

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "core",
        "version": APP_VERSION,
        "phase": REWRITE_PHASE,
        "mode": CORE_MODE,
        "timestamp": _now_iso(),
        "notes": [
            "Legacy business logic has been removed.",
            "This service now bootstraps local SQLite persistence and per-project workspaces.",
        ],
    }


@router.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    return RuntimeCapabilitiesResponse(
        service="core",
        version=APP_VERSION,
        phase=REWRITE_PHASE,
        mode=CORE_MODE,
        retained_surfaces=[
            "health",
            "projects",
            "project_snapshot",
            "project_events",
            "chat",
            "auth_session",
            "asset_import",
            "export",
            "request_id_middleware",
            "cors_for_local_client",
        ],
    )


@router.websocket("/api/v1/projects/{project_id}/events")
async def project_events(websocket: WebSocket, project_id: str) -> None:
    try:
        store.get_project_or_raise(project_id)
    except CoreApiError:
        await websocket.close(code=4404, reason="Project not found")
        return

    await websocket.accept()
    queue = await store.subscribe(project_id)
    try:
        await websocket.send_json(store.snapshot_event(project_id))
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        await store.unsubscribe(project_id, queue)


@router.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "core",
        "phase": REWRITE_PHASE,
        "mode": CORE_MODE,
        "message": "EntroCut core serves an in-memory EditDraft contract for Launchpad, Workspace, chat, and project events.",
        "env": {
            "core_db_path": os.getenv("CORE_DB_PATH", "not_configured"),
            "server_base_url": SERVER_BASE_URL,
        },
    }
