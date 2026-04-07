from __future__ import annotations

import json
from inspect import isawaitable
from typing import Any

from fastapi.responses import StreamingResponse


async def close_upstream_response(response: Any) -> None:
    aclose = getattr(response, "aclose", None)
    if callable(aclose):
        maybe_awaitable = aclose()
        if isawaitable(maybe_awaitable):
            await maybe_awaitable


def chunk_text(content: str, chunk_size: int = 24) -> list[str]:
    normalized = content.strip()
    if not normalized:
        return []
    return [normalized[index : index + chunk_size] for index in range(0, len(normalized), chunk_size)]


async def mock_streaming_chat_response(body: dict[str, Any]) -> StreamingResponse:
    choice = body["choices"][0]
    content = choice["message"]["content"]
    chunks = chunk_text(content)

    async def event_stream():
        for index, piece in enumerate(chunks):
            delta: dict[str, Any] = {"content": piece}
            if index == 0:
                delta["role"] = "assistant"
            chunk_body = {
                "id": body["id"],
                "object": "chat.completion.chunk",
                "created": body["created"],
                "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk_body, ensure_ascii=True)}\n\n"
        final_chunk = {
            "id": body["id"],
            "object": "chat.completion.chunk",
            "created": body["created"],
            "model": body["model"],
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": body["usage"],
            "entro_metadata": body["entro_metadata"],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=True)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
