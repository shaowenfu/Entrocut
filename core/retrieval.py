from __future__ import annotations

from typing import Any

import httpx

from config import SERVER_BASE_URL
from schemas import CoreApiError, EditDraftModel


async def retrieve_candidates(
    *,
    access_token: str,
    project_id: str,
    query_text: str,
    draft: EditDraftModel,
    topk: int = 8,
) -> list[dict[str, Any]]:
    normalized_query = (query_text or "").strip()
    if not normalized_query:
        raise CoreApiError(
            status_code=422,
            code="RETRIEVAL_QUERY_REQUIRED",
            message="retrieve tool requires a non-empty query.",
            details={"project_id": project_id},
        )

    payload = {
        "query_text": normalized_query,
        "topk": max(1, min(topk, 20)),
        "output_fields": [
            "clip_id",
            "asset_id",
            "project_id",
            "source_start_ms",
            "source_end_ms",
            "frame_count",
        ],
        "filter": f'project_id == "{project_id}"',
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(f"{SERVER_BASE_URL}/v1/assets/retrieval", json=payload, headers=headers)

    if response.status_code >= 400:
        raise CoreApiError(
            status_code=502,
            code="RETRIEVAL_SERVER_FAILED",
            message="Server retrieval request failed.",
            details={"server_status": response.status_code, "response": response.text[:300]},
        )

    body = response.json()
    raw_matches = body.get("matches") if isinstance(body, dict) else []
    if not isinstance(raw_matches, list):
        raw_matches = []

    clips_by_id = {clip.id: clip for clip in draft.clips}
    normalized_matches: list[dict[str, Any]] = []
    for item in raw_matches:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        clip_id = str(fields.get("clip_id") or "").strip()
        if not clip_id or clip_id not in clips_by_id:
            continue
        normalized_matches.append(
            {
                "clip_id": clip_id,
                "asset_id": str(fields.get("asset_id") or clips_by_id[clip_id].asset_id),
                "score": float(item.get("score") or 0.0),
                "source_start_ms": int(fields.get("source_start_ms") or clips_by_id[clip_id].source_start_ms),
                "source_end_ms": int(fields.get("source_end_ms") or clips_by_id[clip_id].source_end_ms),
                "frame_count": int(fields.get("frame_count") or 0),
            }
        )
    return normalized_matches
