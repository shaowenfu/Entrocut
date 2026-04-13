from __future__ import annotations

from typing import Any

from helpers import _bump_draft, _entity_id
from schemas import CoreApiError, EditDraftModel, EditDraftPatchModel, SceneModel, ShotModel


def apply_edit_draft_patch(draft: EditDraftModel, patch: EditDraftPatchModel) -> EditDraftModel:
    shots = list(draft.shots)
    clips_by_id = {clip.id: clip for clip in draft.clips}

    def _reorder() -> None:
        for idx, shot in enumerate(shots):
            shots[idx] = shot.model_copy(update={"order": idx})

    for op in patch.operations:
        if op.op == "insert_shot":
            clip_id = (op.clip_id or "").strip()
            if clip_id not in clips_by_id:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_CLIP", message="insert_shot clip_id invalid.")
            clip = clips_by_id[clip_id]
            source_in_ms = op.source_in_ms if op.source_in_ms is not None else clip.source_start_ms
            source_out_ms = op.source_out_ms if op.source_out_ms is not None else min(clip.source_end_ms, source_in_ms + 4000)
            if source_in_ms >= source_out_ms:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_RANGE", message="insert_shot range invalid.")
            insert_at = len(shots) if op.index is None else max(0, min(op.index, len(shots)))
            shots.insert(
                insert_at,
                ShotModel(
                    id=_entity_id("shot"),
                    clip_id=clip_id,
                    source_in_ms=source_in_ms,
                    source_out_ms=source_out_ms,
                    order=insert_at,
                    enabled=True,
                    label=f"Shot {insert_at + 1}",
                    intent=patch.reasoning_summary,
                    note=None,
                    locked_fields=[],
                ),
            )
            _reorder()
        elif op.op == "trim_shot":
            target = next((idx for idx, shot in enumerate(shots) if shot.id == op.shot_id), None)
            if target is None:
                raise CoreApiError(status_code=422, code="PATCH_SHOT_NOT_FOUND", message="trim_shot shot_id missing.")
            source_in_ms = op.source_in_ms if op.source_in_ms is not None else shots[target].source_in_ms
            source_out_ms = op.source_out_ms if op.source_out_ms is not None else shots[target].source_out_ms
            if source_in_ms >= source_out_ms:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_RANGE", message="trim_shot range invalid.")
            shots[target] = shots[target].model_copy(update={"source_in_ms": source_in_ms, "source_out_ms": source_out_ms})
        elif op.op == "delete_shot":
            prior = len(shots)
            shots = [shot for shot in shots if shot.id != op.shot_id]
            if len(shots) == prior:
                raise CoreApiError(status_code=422, code="PATCH_SHOT_NOT_FOUND", message="delete_shot shot_id missing.")
            _reorder()
        elif op.op == "reorder_shot":
            target_index = next((idx for idx, shot in enumerate(shots) if shot.id == op.shot_id), None)
            if target_index is None or op.index is None:
                raise CoreApiError(status_code=422, code="PATCH_SHOT_NOT_FOUND", message="reorder_shot payload invalid.")
            shot = shots.pop(target_index)
            new_index = max(0, min(op.index, len(shots)))
            shots.insert(new_index, shot)
            _reorder()
        elif op.op == "replace_shot":
            target = next((idx for idx, shot in enumerate(shots) if shot.id == op.shot_id), None)
            clip_id = (op.clip_id or "").strip()
            if target is None or clip_id not in clips_by_id:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_OPERATION", message="replace_shot payload invalid.")
            clip = clips_by_id[clip_id]
            source_in_ms = op.source_in_ms if op.source_in_ms is not None else clip.source_start_ms
            source_out_ms = op.source_out_ms if op.source_out_ms is not None else min(clip.source_end_ms, source_in_ms + 4000)
            if source_in_ms >= source_out_ms:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_RANGE", message="replace_shot range invalid.")
            shots[target] = shots[target].model_copy(
                update={"clip_id": clip_id, "source_in_ms": source_in_ms, "source_out_ms": source_out_ms}
            )

    scenes = [
        SceneModel(
            id=_entity_id("scene"),
            shot_ids=[shot.id],
            order=index,
            enabled=True,
            label=shot.label,
            intent=shot.intent,
            note=None,
            locked_fields=[],
        )
        for index, shot in enumerate(shots)
    ]

    selected_shot_id = shots[-1].id if shots else None
    selected_scene_id = scenes[-1].id if scenes else None
    return _bump_draft(
        draft,
        shots=shots,
        scenes=scenes,
        selected_shot_id=selected_shot_id,
        selected_scene_id=selected_scene_id,
        status="ready",
    )
