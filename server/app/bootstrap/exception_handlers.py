from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from ..core.errors import ServerApiError, error_payload, unhandled_error_handler
from ..core.observability import log_event
from .dependencies import logger, metrics, settings


async def logged_unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    log_event(
        logger,
        "unhandled_error",
        service="server",
        env=settings.app_env,
        request_id=request_id,
        error_type=type(exc).__name__,
    )
    return await unhandled_error_handler(request, exc)


async def logged_server_api_error_handler(request: Request, exc: ServerApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    if exc.code.startswith("AUTH_"):
        metrics.inc("server_auth_failures_total", code=exc.code)
    if exc.code == "QUOTA_EXCEEDED":
        metrics.inc("server_quota_exhausted_total")
    if exc.code == "RATE_LIMITED":
        metrics.inc(
            "server_rate_limited_total",
            limit_type=str(exc.details.get("limit_type") or "unknown"),
        )
    log_event(
        logger,
        "server_api_error",
        service="server",
        env=settings.app_env,
        request_id=request_id,
        error_code=exc.code,
        status_code=exc.status_code,
        error_type=exc.error_type,
    )
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc, request_id))


async def dependency_error_handler(request: Request, exc: Exception) -> JSONResponse:
    dependency = "unknown"
    if isinstance(exc, PyMongoError):
        dependency = "mongodb"
    elif isinstance(exc, RedisError):
        dependency = "redis"
    request_id = getattr(request.state, "request_id", None)
    log_event(
        logger,
        "dependency_error",
        service="server",
        env=settings.app_env,
        request_id=request_id,
        dependency=dependency,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": "A required dependency is unavailable.",
                "type": "server_error",
                "details": {"dependency": dependency, "request_id": request_id},
                "request_id": request_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Exception, logged_unhandled_error_handler)
    app.add_exception_handler(ServerApiError, logged_server_api_error_handler)
    app.add_exception_handler(PyMongoError, dependency_error_handler)
    app.add_exception_handler(RedisError, dependency_error_handler)
