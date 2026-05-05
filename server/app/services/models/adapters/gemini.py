from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from ....core.errors import ServerApiError
from ..schemas import ChatRequestContext, NormalizedChatResponse


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part for part in parts if part)
    return ""


def _to_gemini_payload(ctx: ChatRequestContext) -> dict[str, Any]:
    contents: list[dict[str, Any]] = []
    system_parts: list[dict[str, str]] = []
    for message in ctx.payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        text = _extract_text(message.get("content")).strip()
        if not text:
            continue
        role = str(message.get("role") or "user")
        if role == "system":
            system_parts.append({"text": text})
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    payload: dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    generation_config: dict[str, Any] = {}
    if ctx.payload.get("temperature") is not None:
        generation_config["temperature"] = ctx.payload["temperature"]
    if ctx.payload.get("max_tokens") is not None:
        generation_config["maxOutputTokens"] = ctx.payload["max_tokens"]
    if generation_config:
        payload["generationConfig"] = generation_config
    return payload


def _extract_gemini_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    texts = [part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
    return "\n".join(text for text in texts if text)


def _normalize_usage(body: dict[str, Any]) -> dict[str, int]:
    metadata = body.get("usageMetadata")
    if not isinstance(metadata, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt_tokens = int(metadata.get("promptTokenCount") or 0)
    completion_tokens = int(metadata.get("candidatesTokenCount") or 0)
    total_tokens = int(metadata.get("totalTokenCount") or prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


async def send_chat(ctx: ChatRequestContext) -> NormalizedChatResponse:
    model = quote(ctx.effective_model, safe="")
    endpoint_url = f"{ctx.base_url}/models/{model}:generateContent?key={ctx.api_key}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint_url,
                json=_to_gemini_payload(ctx),
                headers={"Content-Type": "application/json", "x-goog-api-client": "entrocut-server/0.1"},
            )
    except httpx.TimeoutException as exc:
        raise ServerApiError(
            status_code=504,
            code="PROVIDER_TIMEOUT",
            message="Gemini provider timed out.",
            error_type="server_error",
        ) from exc
    except httpx.HTTPError as exc:
        raise ServerApiError(
            status_code=502,
            code="PROVIDER_TRANSPORT_ERROR",
            message="Gemini provider transport failed.",
            error_type="server_error",
        ) from exc
    if response.status_code >= 400:
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message="Gemini provider returned an error.",
            error_type="server_error",
            details={"upstream_status": response.status_code, "upstream_body": response.text[:500]},
        )
    body = response.json()
    if not isinstance(body, dict):
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_INVALID_RESPONSE",
            message="Gemini provider returned an invalid response body.",
            error_type="server_error",
        )
    content = _extract_gemini_text(body)
    normalized_body = {
        "id": f"chatcmpl_{uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": ctx.effective_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": _normalize_usage(body),
    }
    return NormalizedChatResponse(body=normalized_body, provider_model=ctx.effective_model)
