from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks
from fastapi.responses import StreamingResponse

from ...core.config import RATE_CARDS, Settings
from ...core.errors import ServerApiError
from ...core.observability import MetricsRegistry, now_ms
from ...repositories.auth_store import AuthStore
from .billing import build_entro_metadata, build_usage, normalize_usage, settle_chat_billing
from .provider_routing import effective_llm_proxy_mode, resolve_chat_provider, resolve_upstream_model
from .streaming import close_upstream_response


def extract_message_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [
                part.get("text", "").strip()
                for part in content
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
            ]
            if parts:
                return " ".join(part for part in parts if part)
    return ""


def estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    return max(1, sum(len(json.dumps(message, ensure_ascii=True)) for message in messages) // 4)


def mock_chat_content(prompt: str, user: dict[str, Any]) -> str:
    prompt_excerpt = prompt[:120] if prompt else "Refine the current cut."
    return (
        f"Editing focus: {prompt_excerpt} "
        f"Use the strongest motion clip as the opener, tighten redundant beats, and end on the clearest payoff. "
        f"Credits balance is {int(user.get('credits_balance') or 0)}."
    )


async def call_upstream_chat(payload: dict[str, Any], *, settings: Settings, metrics: MetricsRegistry) -> dict[str, Any]:
    provider = resolve_chat_provider(settings)
    upstream_payload = dict(payload)
    proxy_mode = effective_llm_proxy_mode(settings)
    if proxy_mode == "google_gemini":
        upstream_payload["model"] = settings.llm_gemini_default_model.strip() or "gemini-2.5-flash"
    else:
        upstream_payload["model"] = resolve_upstream_model(
            settings,
            str(payload.get("model") or settings.llm_default_model),
        )
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    if provider["provider"] == "google_gemini":
        headers["x-goog-api-client"] = "entrocut-server/0.1"
    started_ms = now_ms()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{provider['base_url']}{provider['chat_path']}",
                json=upstream_payload,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        metrics.inc("server_chat_provider_errors_total", provider=provider["provider"], code="timeout")
        raise ServerApiError(
            status_code=504,
            code="PROVIDER_TIMEOUT",
            message="Upstream model provider timed out.",
            error_type="server_error",
            details={"provider": provider["provider"]},
        ) from exc
    except httpx.HTTPError as exc:
        metrics.inc("server_chat_provider_errors_total", provider=provider["provider"], code="transport_error")
        raise ServerApiError(
            status_code=502,
            code="PROVIDER_TRANSPORT_ERROR",
            message="Upstream model provider transport failed.",
            error_type="server_error",
            details={"provider": provider["provider"]},
        ) from exc
    metrics.observe(
        "server_chat_provider_latency_ms",
        now_ms() - started_ms,
        provider=provider["provider"],
        provider_model=str(upstream_payload.get("model") or "unknown"),
    )
    if response.status_code == 429:
        metrics.inc("server_chat_provider_errors_total", provider=provider["provider"], code="429")
        raise ServerApiError(
            status_code=429,
            code="RATE_LIMITED",
            message="Upstream model provider rate limited the request.",
            error_type="rate_limit_error",
            details={"upstream_status": response.status_code, "upstream_body": response.text[:500]},
        )
    if response.status_code >= 400:
        metrics.inc("server_chat_provider_errors_total", provider=provider["provider"], code=str(response.status_code))
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message="Upstream model provider returned an error.",
            error_type="server_error",
            details={"upstream_status": response.status_code, "upstream_body": response.text[:500]},
        )
    body = response.json()
    if not isinstance(body, dict):
        metrics.inc("server_chat_provider_errors_total", provider=provider["provider"], code="invalid_body")
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_INVALID_RESPONSE",
            message="Upstream model provider returned an invalid response body.",
            error_type="server_error",
        )
    return body


def upstream_stream_url_and_headers(settings: Settings) -> tuple[str, dict[str, str]]:
    provider = resolve_chat_provider(settings)
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    if provider["provider"] == "google_gemini":
        headers["x-goog-api-client"] = "entrocut-server/0.1"
    return f"{provider['base_url']}{provider['chat_path']}", headers


async def upstream_chat_stream(
    payload: dict[str, Any],
    *,
    current: dict[str, Any],
    request_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings,
    metrics: MetricsRegistry,
    store: AuthStore,
) -> StreamingResponse:
    upstream_payload = dict(payload)
    proxy_mode = effective_llm_proxy_mode(settings)
    if proxy_mode == "google_gemini":
        upstream_payload["model"] = settings.llm_gemini_default_model.strip() or "gemini-2.5-flash"
    else:
        upstream_payload["model"] = resolve_upstream_model(
            settings,
            str(payload.get("model") or settings.llm_default_model),
        )
    upstream_payload["stream"] = True
    stream_options = upstream_payload.get("stream_options")
    if isinstance(stream_options, dict):
        upstream_payload["stream_options"] = {**stream_options, "include_usage": True}
    else:
        upstream_payload["stream_options"] = {"include_usage": True}
    upstream_url, headers = upstream_stream_url_and_headers(settings)
    exposed_model = str(payload.get("model") or settings.llm_default_model)
    provider_name = resolve_chat_provider(settings)["provider"]
    prompt_tokens = 0
    completion_tokens = 0

    async def event_stream():
        response: Any = None
        started_ms = now_ms()
        nonlocal prompt_tokens, completion_tokens
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                stream_context = client.stream("POST", upstream_url, json=upstream_payload, headers=headers)
                try:
                    async with stream_context as response:
                        if response.status_code == 429:
                            metrics.inc("server_chat_provider_errors_total", provider=provider_name, code="429")
                            raise ServerApiError(
                                status_code=429,
                                code="RATE_LIMITED",
                                message="Upstream model provider rate limited the request.",
                                error_type="rate_limit_error",
                                details={"upstream_status": response.status_code},
                            )
                        if response.status_code >= 400:
                            body = await response.aread()
                            metrics.inc("server_chat_provider_errors_total", provider=provider_name, code=str(response.status_code))
                            raise ServerApiError(
                                status_code=502,
                                code="MODEL_PROVIDER_UNAVAILABLE",
                                message="Upstream model provider returned an error.",
                                error_type="server_error",
                                details={
                                    "upstream_status": response.status_code,
                                    "upstream_body": body.decode("utf-8", errors="ignore")[:500],
                                },
                            )
                        async for raw_line in response.aiter_lines():
                            line = raw_line.strip()
                            if not line:
                                continue
                            if line.startswith("data:"):
                                data = line[5:].strip()
                                if data and data != "[DONE]":
                                    try:
                                        chunk_body = json.loads(data)
                                    except json.JSONDecodeError:
                                        chunk_body = None
                                    if isinstance(chunk_body, dict):
                                        usage = normalize_usage(chunk_body.get("usage"))
                                        if usage is not None:
                                            prompt_tokens = int(usage.get("prompt_tokens") or 0)
                                            completion_tokens = int(usage.get("completion_tokens") or 0)
                            yield f"{line}\n\n"
                finally:
                    if response is not None:
                        await close_upstream_response(response)
        except httpx.TimeoutException as exc:
            metrics.inc("server_chat_provider_errors_total", provider=provider_name, code="timeout")
            raise ServerApiError(
                status_code=504,
                code="PROVIDER_TIMEOUT",
                message="Upstream model provider timed out.",
                error_type="server_error",
                details={"provider": provider_name},
            ) from exc
        except httpx.HTTPError as exc:
            metrics.inc("server_chat_provider_errors_total", provider=provider_name, code="transport_error")
            raise ServerApiError(
                status_code=502,
                code="PROVIDER_TRANSPORT_ERROR",
                message="Upstream model provider transport failed.",
                error_type="server_error",
                details={"provider": provider_name},
            ) from exc
        finally:
            metrics.observe(
                "server_chat_provider_latency_ms",
                now_ms() - started_ms,
                provider=provider_name,
                provider_model=str(upstream_payload.get("model") or "unknown"),
            )

    def settle_stream_usage() -> None:
        settle_chat_billing(
            current=current,
            request_id=request_id,
            model=exposed_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider=provider_name,
            rate_cards=RATE_CARDS,
            store=store,
        )

    background_tasks.add_task(settle_stream_usage)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def build_chat_completion_payload(
    payload: dict[str, Any],
    current: dict[str, Any],
    *,
    settings: Settings,
    metrics: MetricsRegistry,
) -> dict[str, Any]:
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

    if effective_llm_proxy_mode(settings) in {"upstream", "google_gemini"}:
        body = await call_upstream_chat(payload, settings=settings, metrics=metrics)
        provider_model = str(body.get("model")) if body.get("model") else None
        usage = normalize_usage(body.get("usage"))
        body["model"] = str(payload.get("model") or settings.llm_default_model)
        if provider_model:
            body["_provider_model"] = provider_model
        if usage:
            body["usage"] = usage
        body["entro_metadata"] = build_entro_metadata(current["user"])
        if not usage:
            body["usage"] = build_usage(messages, json.dumps(body.get("choices", []), ensure_ascii=True))
        return body

    prompt = extract_message_text(messages)
    content = mock_chat_content(prompt, current["user"])
    usage = build_usage(messages, content)
    return {
        "id": f"chatcmpl_{uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(payload.get("model") or settings.llm_default_model),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
        "entro_metadata": build_entro_metadata(current["user"]),
    }
