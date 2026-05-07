from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

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


def _load_genai_modules() -> tuple[Any, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ServerApiError(
            status_code=503,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message="google-genai is required for Gemini provider.",
            error_type="server_error",
        ) from exc
    return genai, types


def _content_from_message(message: dict[str, Any], types: Any) -> Any | None:
    text = _extract_text(message.get("content")).strip()
    if not text:
        return None
    role = "model" if str(message.get("role") or "user") == "assistant" else "user"
    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


def _build_generation_config(ctx: ChatRequestContext, types: Any, *, system_instruction: str | None) -> Any:
    config: dict[str, Any] = {}
    if system_instruction:
        config["system_instruction"] = system_instruction
    if ctx.payload.get("temperature") is not None:
        config["temperature"] = ctx.payload["temperature"]
    if ctx.payload.get("max_tokens") is not None:
        config["max_output_tokens"] = ctx.payload["max_tokens"]
    return types.GenerateContentConfig(**config) if config else None


def _normalize_usage(response: Any) -> dict[str, int]:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
    completion_tokens = int(getattr(metadata, "candidates_token_count", 0) or 0)
    total_tokens = int(getattr(metadata, "total_token_count", 0) or prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


async def _close_client(client: Any) -> None:
    async_client = getattr(client, "aio", None)
    aclose = getattr(async_client, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(client, "close", None)
    if callable(close):
        close()


async def send_chat(ctx: ChatRequestContext) -> NormalizedChatResponse:
    genai, types = _load_genai_modules()
    contents: list[Any] = []
    system_parts: list[str] = []
    for message in ctx.payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "user") == "system":
            text = _extract_text(message.get("content")).strip()
            if text:
                system_parts.append(text)
            continue
        content = _content_from_message(message, types)
        if content is not None:
            contents.append(content)
    if not contents:
        raise ServerApiError(
            status_code=422,
            code="INVALID_CHAT_MESSAGES",
            message="Gemini provider requires at least one non-empty user or assistant message.",
            error_type="invalid_request_error",
        )

    client = genai.Client(api_key=ctx.api_key)
    try:
        response = await client.aio.models.generate_content(
            model=ctx.effective_model,
            contents=contents,
            config=_build_generation_config(
                ctx,
                types,
                system_instruction="\n\n".join(system_parts) if system_parts else None,
            ),
        )
    except TimeoutError as exc:
        raise ServerApiError(
            status_code=504,
            code="PROVIDER_TIMEOUT",
            message="Gemini provider timed out.",
            error_type="server_error",
        ) from exc
    except Exception as exc:
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message=f"Gemini provider request failed: {exc}",
            error_type="server_error",
        ) from exc
    finally:
        await _close_client(client)

    content = str(getattr(response, "text", "") or "")
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
        "usage": _normalize_usage(response),
    }
    return NormalizedChatResponse(body=normalized_body, provider_model=ctx.effective_model)
