from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import SERVER_BASE_URL
from contracts import ClipModel, CoreApiError, EditDraftModel
from media.ingestion import extract_and_stitch_frames


DEFAULT_DESCRIBE_QUESTION = (
    "Describe the visible subjects, actions, scene, camera movement, mood, and editing value of this clip. "
    "Mention uncertainty and do not invent details."
)


def inspect_candidate(*, clip: ClipModel, retrieval_score: float | None = None) -> dict[str, Any]:
    score = 0.0 if retrieval_score is None else float(retrieval_score)
    return {
        "clip": clip.model_dump(),
        "retrieval_score": round(score, 4),
        "thumbnail_ref": clip.thumbnail_ref,
        "source_range": {"start_ms": clip.source_start_ms, "end_ms": clip.source_end_ms},
        "summary": f"{clip.visual_desc} ({clip.source_start_ms}-{clip.source_end_ms}ms)",
        "why_selected": "semantic_match_and_retrieval_score",
    }


def pick_clip_for_inspect(*, clip_id: str | None, candidate_clip_ids: list[str], clips: list[ClipModel]) -> ClipModel:
    clips_by_id = {clip.id: clip for clip in clips}
    if clip_id and clip_id in clips_by_id:
        return clips_by_id[clip_id]
    for candidate_id in candidate_clip_ids:
        if candidate_id in clips_by_id:
            return clips_by_id[candidate_id]
    if clips:
        return clips[0]
    raise CoreApiError(
        status_code=502,
        code="TOOL_EXECUTION_FAILED",
        message="Inspect tool could not find any clip in draft.",
    )


async def describe_clip_with_server(
    *,
    access_token: str,
    project_id: str,
    draft: EditDraftModel,
    clip: ClipModel,
    question: str | None = None,
    task_summary: str | None = None,
) -> dict[str, Any]:
    asset = next((item for item in draft.assets if item.id == clip.asset_id), None)
    if asset is None or not asset.source_path:
        raise CoreApiError(
            status_code=502,
            code="INSPECT_EVIDENCE_UNAVAILABLE",
            message="Inspect describe requires a source asset path for frame evidence.",
            details={"project_id": project_id, "clip_id": clip.id, "asset_id": clip.asset_id},
        )

    image_base64 = await asyncio.to_thread(
        extract_and_stitch_frames,
        asset.source_path,
        clip.source_start_ms,
        clip.source_end_ms,
    )
    payload = {
        "mode": "describe",
        "task_summary": (task_summary or "Agent needs visual understanding before making an editing decision.").strip(),
        "question": (question or DEFAULT_DESCRIBE_QUESTION).strip(),
        "candidates": [
            {
                "clip_id": clip.id,
                "asset_id": clip.asset_id,
                "clip_duration_ms": max(1, int(clip.source_end_ms) - int(clip.source_start_ms)),
                "summary": clip.visual_desc,
                "frames": [
                    {
                        "frame_index": 0,
                        "timestamp_ms": 0,
                        "timestamp_label": "stitched_keyframes",
                        "image_base64": image_base64,
                    }
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(f"{SERVER_BASE_URL}/v1/tools/inspect", json=payload, headers=headers)

    if response.status_code >= 400:
        raise CoreApiError(
            status_code=502,
            code="INSPECT_SERVER_FAILED",
            message="Server inspect describe request failed.",
            details={
                "project_id": project_id,
                "clip_id": clip.id,
                "server_status": response.status_code,
                "response": response.text[:500],
            },
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise CoreApiError(
            status_code=502,
            code="INSPECT_SERVER_INVALID_RESPONSE",
            message="Server inspect describe response was not JSON.",
            details={"project_id": project_id, "clip_id": clip.id},
        ) from exc
    if not isinstance(body, dict):
        raise CoreApiError(
            status_code=502,
            code="INSPECT_SERVER_INVALID_RESPONSE",
            message="Server inspect describe response must be an object.",
            details={"project_id": project_id, "clip_id": clip.id},
        )
    return {
        "mode": "describe",
        "clip": clip.model_dump(),
        "source_range": {"start_ms": clip.source_start_ms, "end_ms": clip.source_end_ms},
        "thumbnail_ref": clip.thumbnail_ref,
        "question": payload["question"],
        "server_response": body,
        "summary": _summarize_describe_response(body, fallback=clip.visual_desc),
    }


def _summarize_describe_response(body: dict[str, Any], *, fallback: str) -> str:
    descriptions = body.get("descriptions")
    if isinstance(descriptions, list) and descriptions:
        first = descriptions[0]
        if isinstance(first, dict):
            description = str(first.get("description") or "").strip()
            if description:
                return description
    return fallback
