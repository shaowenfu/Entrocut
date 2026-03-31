from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from ...bootstrap.dependencies import (
    RATE_CARDS,
    get_current_user,
    logger,
    metrics,
    provider_dependency_status,
    rate_limit_service,
    request_id,
    settings,
    store,
)
from ...core.observability import log_audit_event, log_event
from ...core.errors import ServerApiError
from ...services.gateway.billing import build_entro_metadata, settle_chat_billing, stored_user_id
from ...services.gateway.chat_proxy import build_chat_completion_payload, estimate_prompt_tokens, upstream_chat_stream
from ...services.gateway.provider_routing import effective_llm_proxy_mode
from ...services.gateway.streaming import mock_streaming_chat_response


router = APIRouter(tags=["chat"])


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    current: dict = Depends(get_current_user),
):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ServerApiError(
            status_code=422,
            code="INVALID_CHAT_REQUEST",
            message="Request body must be a JSON object.",
            error_type="invalid_request_error",
        )
    if current["user"].get("status") != "active":
        raise ServerApiError(
            status_code=403,
            code="USER_SUSPENDED",
            message="The current user is suspended.",
            error_type="auth_error",
        )
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ServerApiError(
            status_code=422,
            code="INVALID_CHAT_MESSAGES",
            message="messages must be a non-empty array.",
            error_type="invalid_request_error",
        )
    stream_options = payload.get("stream_options")
    if isinstance(stream_options, dict):
        payload["stream_options"] = {**stream_options, "include_usage": True}
    else:
        payload["stream_options"] = {"include_usage": True}
    if int(current["user"].get("credits_balance") or 0) <= 0:
        raise ServerApiError(
            status_code=402,
            code="INSUFFICIENT_CREDITS",
            message="Insufficient credits balance.",
            error_type="payment_required",
        )
    rate_limit_service.consume_prompt_budget(
        user_id=stored_user_id(current["user"]),
        prompt_tokens=estimate_prompt_tokens(messages),
    )
    current_request_id = getattr(request.state, "request_id", None) or request_id()
    provider_name = provider_dependency_status().get("mode", effective_llm_proxy_mode(settings))
    log_event(
        logger,
        "chat_request_started",
        service="server",
        env=settings.app_env,
        request_id=current_request_id,
        user_id=current["user"]["_id"],
        session_id=current["token_payload"]["sid"],
        model=str(payload.get("model") or settings.llm_default_model),
        provider=provider_name,
        stream=bool(payload.get("stream") is True),
    )
    if payload.get("stream") is True and effective_llm_proxy_mode(settings) != "mock":
        metrics.inc(
            "server_chat_requests_total",
            stream="true",
            model=str(payload.get("model") or settings.llm_default_model),
            provider=provider_name,
            status="accepted",
        )
        return await upstream_chat_stream(
            payload,
            current=current,
            request_id=current_request_id,
            background_tasks=background_tasks,
            settings=settings,
            metrics=metrics,
            store=store,
        )
    body = await build_chat_completion_payload(payload, current, settings=settings, metrics=metrics)
    usage = body.get("usage") if isinstance(body, dict) else None
    prompt_tokens = int((usage or {}).get("prompt_tokens") or 0) if isinstance(usage, dict) else 0
    completion_tokens = int((usage or {}).get("completion_tokens") or 0) if isinstance(usage, dict) else 0
    credits_balance = settle_chat_billing(
        current=current,
        request_id=current_request_id,
        model=str(payload.get("model") or settings.llm_default_model),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        provider=provider_name,
        rate_cards=RATE_CARDS,
        store=store,
    )
    if isinstance(usage, dict):
        rate_limit_service.add_completion_tokens(
            user_id=stored_user_id(current["user"]),
            completion_tokens=completion_tokens,
        )
    if isinstance(body, dict):
        body["entro_metadata"] = build_entro_metadata(current["user"])
        body["entro_metadata"]["credits_balance"] = credits_balance
    log_event(
        logger,
        "chat_request_succeeded",
        service="server",
        env=settings.app_env,
        request_id=current_request_id,
        user_id=current["user"]["_id"],
        session_id=current["token_payload"]["sid"],
        model=str(payload.get("model") or settings.llm_default_model),
        provider=provider_name,
        stream=bool(payload.get("stream") is True),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        credits_balance=credits_balance,
    )
    log_audit_event(
        "audit_chat_usage_recorded",
        env=settings.app_env,
        request_id=current_request_id,
        actor_user_id=current["user"]["_id"],
        actor_session_id=current["token_payload"]["sid"],
        action="chat.completions.consume",
        result="success",
        target_type="credit_ledger",
        target_id=current_request_id,
        details={
            "model": str(payload.get("model") or settings.llm_default_model),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "credits_balance": credits_balance,
        },
    )
    metrics.inc(
        "server_chat_requests_total",
        stream="true" if payload.get("stream") is True else "false",
        model=str(payload.get("model") or settings.llm_default_model),
        provider=provider_name,
        status="success",
    )
    if payload.get("stream") is True:
        return await mock_streaming_chat_response(body)
    return JSONResponse(content=body)
