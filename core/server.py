from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import AGENT_LOOP_MAX_ITERATIONS, APP_VERSION, REWRITE_PHASE
from helpers import _request_id
from routers import api_router
from routers.projects import set_agent_loop_max_iterations_resolver
from schemas import CoreApiError, ErrorBody, ErrorEnvelope
from store import CoreAuthSessionStore, InMemoryProjectStore, auth_session_store, store

app = FastAPI(title="EntroCut Core In-Memory", version=APP_VERSION)
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

set_agent_loop_max_iterations_resolver(lambda: AGENT_LOOP_MAX_ITERATIONS)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or _request_id()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(CoreApiError)
async def core_api_error_handler(request: Request, exc: CoreApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorEnvelope(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=getattr(request.state, "request_id", None),
            )
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error=ErrorBody(
                code="CORE_IN_MEMORY_UNHANDLED",
                message=str(exc) or "Unhandled in-memory core error.",
                details={"phase": REWRITE_PHASE},
                request_id=getattr(request.state, "request_id", None),
            )
        ).model_dump(),
    )


app.include_router(api_router)
