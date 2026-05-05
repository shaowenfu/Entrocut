from __future__ import annotations

from typing import Any

import httpx

from ....core.errors import ServerApiError
from ..schemas import ChatRequestContext, NormalizedChatResponse


async def send_chat(ctx: ChatRequestContext) -> NormalizedChatResponse:
    headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}
    upstream_payload = dict(ctx.payload)
    upstream_payload.pop("provider", None)
    upstream_payload.pop("custom_model", None)
    upstream_payload["model"] = ctx.effective_model
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{ctx.base_url}{ctx.chat_path}", json=upstream_payload, headers=headers)
    except httpx.HTTPError as exc:
        raise ServerApiError(status_code=502, code="PROVIDER_TRANSPORT_ERROR", message="Upstream model provider transport failed.", error_type="server_error") from exc
    if response.status_code >= 400:
        raise ServerApiError(status_code=502, code="MODEL_PROVIDER_UNAVAILABLE", message="Upstream model provider returned an error.", error_type="server_error")
    body = response.json()
    if not isinstance(body, dict):
        raise ServerApiError(status_code=502, code="MODEL_PROVIDER_INVALID_RESPONSE", message="Upstream model provider returned an invalid response body.", error_type="server_error")
    body["model"] = ctx.effective_model
    return NormalizedChatResponse(body=body, provider_model=str(body.get("model") or ctx.effective_model))
