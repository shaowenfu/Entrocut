from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ...bootstrap.dependencies import (
    get_current_user,
    logger,
    metrics,
    quota_service,
    rate_limit_service,
    request_id,
    settings,
)
from ...core.observability import log_audit_event, log_event
from ...core.errors import ServerApiError
from ...services.gateway.billing import build_entro_metadata, build_usage, normalize_usage, stored_user_id
from ...services.models.gateway import chat as gateway_chat


router = APIRouter(tags=["chat"])


def estimate_prompt_tokens(messages: list[dict]) -> int:
    return max(1, sum(len(json.dumps(message, ensure_ascii=True)) for message in messages) // 4)


def effective_request_model(payload: dict) -> str:
    return str(payload.get("custom_model") or payload.get("model") or settings.llm_default_model)


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
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
    quota_service.assert_can_chat(current["user"])
    rate_limit_service.consume_prompt_budget(
        user_id=stored_user_id(current["user"]),
        prompt_tokens=estimate_prompt_tokens(messages),
    )
    current_request_id = getattr(request.state, "request_id", None) or request_id()
    provider_name = str(payload.get("provider") or "deepseek")
    log_event(
        logger,
        "chat_request_started",
        service="server",
        env=settings.app_env,
        request_id=current_request_id,
        user_id=current["user"]["_id"],
        session_id=current["token_payload"]["sid"],
        model=effective_request_model(payload),
        provider=provider_name,
        stream=bool(payload.get("stream") is True),
    )
    gateway_response = await gateway_chat(payload, settings)
    body = gateway_response.body
    if gateway_response.provider_model:
        body["_provider_model"] = gateway_response.provider_model
    usage = normalize_usage(body.get("usage")) if isinstance(body, dict) else None
    if usage is None:
        usage = build_usage(messages, json.dumps(body.get("choices", []), ensure_ascii=True))
        body["usage"] = usage
    else:
        body["usage"] = usage
    prompt_tokens = int((usage or {}).get("prompt_tokens") or 0) if isinstance(usage, dict) else 0
    completion_tokens = int((usage or {}).get("completion_tokens") or 0) if isinstance(usage, dict) else 0
    quota_service.record_chat_usage(
        user=current["user"],
        session_id=str(current["token_payload"]["sid"]),
        request_id=current_request_id,
        exposed_model=effective_request_model(payload),
        provider_model=str(body.get("_provider_model")) if isinstance(body, dict) and body.get("_provider_model") else None,
        usage=usage if isinstance(usage, dict) else None,
    )
    credits_balance = int(current["user"].get("remaining_quota") or 0)
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
        model=effective_request_model(payload),
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
            "model": effective_request_model(payload),
            "selected_model": str(payload.get("model") or settings.llm_default_model),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "credits_balance": credits_balance,
        },
    )
    metrics.inc(
        "server_chat_requests_total",
        stream="true" if payload.get("stream") is True else "false",
        model=effective_request_model(payload),
        provider=provider_name,
        status="success",
    )
    return JSONResponse(content=body)
