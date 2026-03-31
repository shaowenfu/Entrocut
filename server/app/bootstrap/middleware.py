from __future__ import annotations

from fastapi import FastAPI, Request

from ..core.observability import log_event, now_ms
from .dependencies import logger, metrics, request_id, settings


async def request_context_middleware(request: Request, call_next):
    current_request_id = request.headers.get("x-request-id", "").strip() or request_id()
    request.state.request_id = current_request_id
    started_ms = now_ms()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = current_request_id
        return response
    except Exception:
        metrics.inc(
            "server_http_requests_total",
            route=request.url.path,
            method=request.method,
            status_code=str(status_code),
        )
        metrics.observe(
            "server_http_request_duration_ms",
            now_ms() - started_ms,
            route=request.url.path,
            method=request.method,
            status_code=str(status_code),
        )
        log_event(
            logger,
            "request_failed",
            service="server",
            env=settings.app_env,
            request_id=current_request_id,
            route=request.url.path,
            method=request.method,
            status_code=status_code,
            latency_ms=round(now_ms() - started_ms, 2),
        )
        raise
    finally:
        if "response" in locals():
            metrics.inc(
                "server_http_requests_total",
                route=request.url.path,
                method=request.method,
                status_code=str(status_code),
            )
            metrics.observe(
                "server_http_request_duration_ms",
                now_ms() - started_ms,
                route=request.url.path,
                method=request.method,
                status_code=str(status_code),
            )
            log_event(
                logger,
                "request_completed",
                service="server",
                env=settings.app_env,
                request_id=current_request_id,
                route=request.url.path,
                method=request.method,
                status_code=status_code,
                latency_ms=round(now_ms() - started_ms, 2),
            )


def register_middleware(app: FastAPI) -> None:
    app.middleware("http")(request_context_middleware)
