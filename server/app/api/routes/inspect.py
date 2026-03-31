from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from ...bootstrap.dependencies import get_current_user, inspect_service, logger, metrics, settings
from ...core.errors import ServerApiError
from ...core.observability import log_audit_event, log_event, now_ms
from ...schemas.inspect import InspectResponse


router = APIRouter(tags=["inspect"])


@router.post("/v1/tools/inspect", response_model=InspectResponse)
async def tools_inspect(
    request: Request,
    current: dict = Depends(get_current_user),
) -> InspectResponse:
    try:
        raw_payload = await request.json()
    except json.JSONDecodeError as exc:
        raise ServerApiError(
            status_code=422,
            code="INVALID_INSPECT_REQUEST",
            message="Request body must be valid JSON.",
            error_type="invalid_request_error",
        ) from exc

    payload = inspect_service.validate_request(raw_payload)
    request_id = getattr(request.state, "request_id", None)
    provider_name = inspect_service.peek_provider_name()
    started_ms = now_ms()

    log_event(
        logger,
        "inspect_started",
        service="server",
        env=settings.app_env,
        request_id=request_id,
        user_id=current["user"]["_id"],
        mode=payload.mode,
        candidate_count=len(payload.candidates),
        provider=provider_name,
    )
    try:
        result = await inspect_service.inspect(payload)
    except ServerApiError as exc:
        metrics.inc("server_inspect_requests_total", status="error", mode=payload.mode)
        log_event(
            logger,
            "inspect_failed",
            service="server",
            env=settings.app_env,
            request_id=request_id,
            user_id=current["user"]["_id"],
            mode=payload.mode,
            candidate_count=len(payload.candidates),
            provider=provider_name,
            error_code=exc.code,
        )
        raise

    metrics.inc("server_inspect_requests_total", status="success", mode=payload.mode)
    metrics.observe(
        "server_inspect_provider_latency_ms",
        now_ms() - started_ms,
        provider=provider_name,
        mode=payload.mode,
    )
    log_event(
        logger,
        "inspect_succeeded",
        service="server",
        env=settings.app_env,
        request_id=request_id,
        user_id=current["user"]["_id"],
        mode=payload.mode,
        candidate_count=len(payload.candidates),
        provider=provider_name,
        selected_clip_id=result.selected_clip_id,
    )
    log_audit_event(
        "audit_inspect_succeeded",
        env=settings.app_env,
        request_id=request_id,
        actor_user_id=current["user"]["_id"],
        action="tools.inspect",
        result="success",
        target_type="inspect_request",
        target_id=request_id,
        details={
            "mode": payload.mode,
            "candidate_count": len(payload.candidates),
            "selected_clip_id": result.selected_clip_id,
        },
    )
    return result
