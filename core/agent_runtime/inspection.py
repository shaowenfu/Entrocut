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
    inspection_goal: str,
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
        "clip_id": clip.id,
        "prompt": _build_inspect_prompt(inspection_goal=inspection_goal),
        "image_base64": image_base64,
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
        "clip_id": clip.id,
        "inspection_goal": inspection_goal,
        "visual_description": _summarize_describe_response(body, fallback=clip.visual_desc),
        "uncertainty": str(body.get("uncertainty") or "none"),
        "evidence_frame_count": 4,
    }


def _summarize_describe_response(body: dict[str, Any], *, fallback: str) -> str:
    description = str(body.get("description") or "").strip()
    if description:
        return description
    return fallback


def _build_inspect_prompt(*, inspection_goal: str) -> str:
    goal_text = inspection_goal.strip()
    return f"{goal_text}\n\n{DEFAULT_DESCRIBE_QUESTION}".strip()
