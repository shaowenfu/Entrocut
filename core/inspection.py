from __future__ import annotations

from typing import Any

from schemas import ClipModel, CoreApiError


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
