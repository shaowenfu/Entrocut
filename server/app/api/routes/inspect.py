from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...bootstrap.dependencies import get_current_user, inspect_service, logger, metrics, settings
from ...core.errors import ServerApiError
from ...core.observability import log_audit_event, log_event, now_ms
from ...schemas.inspect import InspectRequest, InspectResponse


router = APIRouter(tags=["inspect"])


@router.post("/v1/tools/inspect", response_model=InspectResponse)
async def tools_inspect(
    request: Request,
    payload_body: InspectRequest,
    current: dict = Depends(get_current_user),
) -> InspectResponse:
    payload = inspect_service.validate_request(payload_body.model_dump())
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
