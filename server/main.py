from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

APP_VERSION = "0.6.0-skeleton"
REWRITE_PHASE = "clean_room_rewrite"

app = FastAPI(title="EntroCut Server Skeleton", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


class RuntimeCapabilitiesResponse(BaseModel):
    service: str
    version: str
    phase: str
    mode: str
    retained_surfaces: list[str]


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or _request_id()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error={
                "code": "SERVER_SKELETON_UNHANDLED",
                "message": str(exc) or "Unhandled skeleton error.",
                "details": {"phase": REWRITE_PHASE},
            }
        ).model_dump(),
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "server",
        "version": APP_VERSION,
        "phase": REWRITE_PHASE,
        "mode": "skeleton",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "notes": [
            "Legacy orchestration logic has been removed.",
            "Use this surface only as the clean starting point for auth/proxy rebuild.",
        ],
    }


@app.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    return RuntimeCapabilitiesResponse(
        service="server",
        version=APP_VERSION,
        phase=REWRITE_PHASE,
        mode="skeleton",
        retained_surfaces=[
            "health",
            "runtime_capabilities",
            "request_id_middleware",
            "cors_for_local_client",
        ],
    )


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "server",
        "phase": REWRITE_PHASE,
        "message": "EntroCut server is now a clean-room skeleton. Rebuild auth/proxy contracts from scratch.",
        "env": {
            "server_db_path": os.getenv("SERVER_DB_PATH", "not_configured"),
            "auth_jwt_algorithm": os.getenv("AUTH_JWT_ALGORITHM", "HS256"),
        },
    }
