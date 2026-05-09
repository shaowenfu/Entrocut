from __future__ import annotations

from contracts import CoreApiError, EditDraftModel, EditDraftPatchModel, SceneModel, ShotModel
from runtime.helpers import _bump_draft, _entity_id


def apply_edit_draft_patch(draft: EditDraftModel, patch: EditDraftPatchModel) -> EditDraftModel:
    shots = list(draft.shots)
    scenes = list(draft.scenes or [])
    clips_by_id = {clip.id: clip for clip in draft.clips}
    selected_shot_id = draft.selected_shot_id
    selected_scene_id = draft.selected_scene_id

    def _reorder_shots() -> None:
        for index, shot in enumerate(shots):
            shots[index] = shot.model_copy(update={"order": index})

    def _scene_index(scene_id: str) -> int:
        if scene_id == "root" and not scenes:
            scenes.append(
                SceneModel(
                    id=_entity_id("scene"),
                    shot_ids=[],
                    order=0,
                    enabled=True,
                    label="Scene 1",
                    intent="",
                    note=None,
                    locked_fields=[],
                )
            )
            return 0
        index = next((idx for idx, scene in enumerate(scenes) if scene.id == scene_id), None)
        if index is None:
            raise CoreApiError(status_code=422, code="PATCH_SCENE_NOT_FOUND", message="insert_shot scene_id missing.")
        return index

    def _shot_index(shot_id: str) -> int:
        index = next((idx for idx, shot in enumerate(shots) if shot.id == shot_id), None)
        if index is None:
            raise CoreApiError(status_code=422, code="PATCH_SHOT_NOT_FOUND", message="patch shot_id missing.")
        return index

    def _global_insert_index(scene_shot_ids: list[str], index: int) -> int:
        if not scene_shot_ids:
            return len(shots)
        bounded = max(0, min(index, len(scene_shot_ids)))
        if bounded < len(scene_shot_ids):
            return _shot_index(scene_shot_ids[bounded])
        return _shot_index(scene_shot_ids[-1]) + 1

    for op in patch.operations:
        if op.op == "insert_shot":
            scene_id = (op.scene_id or "").strip()
            clip_id = (op.clip_id or "").strip()
            if clip_id not in clips_by_id:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_CLIP", message="insert_shot clip_id invalid.")
            scene_idx = _scene_index(scene_id)
            scene = scenes[scene_idx]
            source_in_ms = op.source_in_ms if op.source_in_ms is not None else clips_by_id[clip_id].source_start_ms
            source_out_ms = op.source_out_ms if op.source_out_ms is not None else clips_by_id[clip_id].source_end_ms
            if source_in_ms >= source_out_ms:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_RANGE", message="insert_shot range invalid.")
            scene_insert_at = op.index if op.index is not None else len(scene.shot_ids)
            global_insert_at = _global_insert_index(scene.shot_ids, scene_insert_at)
            new_shot = ShotModel(
                id=_entity_id("shot"),
                clip_id=clip_id,
                source_in_ms=source_in_ms,
                source_out_ms=source_out_ms,
                order=global_insert_at,
                enabled=True,
                label=f"Shot {global_insert_at + 1}",
                intent=(op.intent or "").strip(),
                note=None,
                locked_fields=[],
            )
            shots.insert(global_insert_at, new_shot)
            next_scene_shot_ids = list(scene.shot_ids)
            next_scene_shot_ids.insert(max(0, min(scene_insert_at, len(next_scene_shot_ids))), new_shot.id)
            scenes[scene_idx] = scene.model_copy(update={"shot_ids": next_scene_shot_ids})
            selected_shot_id = new_shot.id
            selected_scene_id = scene.id
            _reorder_shots()
            continue

        if op.op == "replace_shot":
            target_idx = _shot_index((op.shot_id or "").strip())
            clip_id = (op.clip_id or "").strip()
            if clip_id not in clips_by_id:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_CLIP", message="replace_shot clip_id invalid.")
            source_in_ms = op.source_in_ms if op.source_in_ms is not None else clips_by_id[clip_id].source_start_ms
            source_out_ms = op.source_out_ms if op.source_out_ms is not None else clips_by_id[clip_id].source_end_ms
            if source_in_ms >= source_out_ms:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_RANGE", message="replace_shot range invalid.")
            shots[target_idx] = shots[target_idx].model_copy(
                update={
                    "clip_id": clip_id,
                    "source_in_ms": source_in_ms,
                    "source_out_ms": source_out_ms,
                    "intent": (op.intent or shots[target_idx].intent or "").strip(),
                }
            )
            selected_shot_id = shots[target_idx].id
            selected_scene_id = next((scene.id for scene in scenes if selected_shot_id in scene.shot_ids), selected_scene_id)
            continue

        if op.op == "delete_shot":
            shot_id = (op.shot_id or "").strip()
            _shot_index(shot_id)
            shots = [shot for shot in shots if shot.id != shot_id]
            next_scenes = []
            for scene in scenes:
                next_scenes.append(scene.model_copy(update={"shot_ids": [item for item in scene.shot_ids if item != shot_id]}))
            scenes = next_scenes
            selected_shot_id = shots[-1].id if shots else None
            selected_scene_id = next((scene.id for scene in scenes if selected_shot_id in scene.shot_ids), None)
            _reorder_shots()
            continue

    return _bump_draft(
        draft,
        shots=shots,
        scenes=scenes,
        selected_shot_id=selected_shot_id,
        selected_scene_id=selected_scene_id,
        status="ready" if shots else "draft",
    )
