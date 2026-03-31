from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from schemas import (
    AssetModel,
    AssetProcessingStage,
    AssetType,
    ClipModel,
    EditDraftModel,
    MediaFileReference,
    MediaReference,
    SceneModel,
    ShotModel,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _entity_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"].strip())
        return " ".join(part for part in parts if part)
    return ""


def _derive_title(title: str | None, prompt: str | None, media: MediaReference | None) -> str:
    explicit = _trimmed(title)
    if explicit:
        return explicit
    normalized_prompt = _trimmed(prompt)
    if normalized_prompt:
        return normalized_prompt[:48]
    if media and media.folder_path:
        return Path(media.folder_path).name or "Untitled Project"
    if media and media.files:
        return media.files[0].name
    return "Untitled Project"


def _media_file_refs(media: MediaReference) -> list[MediaFileReference]:
    if media.files:
        return media.files
    if media.folder_path:
        folder_name = Path(media.folder_path).name or "media"
        return [MediaFileReference(name=f"{folder_name}.mp4", path=media.folder_path)]
    return []


def _build_assets(
    media: MediaReference,
    *,
    processing_stage: AssetProcessingStage = "pending",
    processing_progress: int | None = None,
    updated_at: str | None = None,
) -> list[AssetModel]:
    assets: list[AssetModel] = []
    for index, file_ref in enumerate(_media_file_refs(media), start=1):
        name = file_ref.name.strip()
        if not name:
            continue
        asset_type: AssetType = "audio" if name.lower().endswith((".mp3", ".wav", ".aac")) else "video"
        duration_seconds = 18 + index * 7
        assets.append(
            AssetModel(
                id=_entity_id("asset"),
                name=name,
                duration_ms=duration_seconds * 1000,
                type=asset_type,
                source_path=file_ref.path.strip() if file_ref.path and file_ref.path.strip() else None,
                processing_stage=processing_stage,
                processing_progress=processing_progress,
                clip_count=0,
                indexed_clip_count=0,
                last_error=None,
                updated_at=updated_at,
            )
        )
    return assets


def _asset_clip_counts(clips: list[ClipModel]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for clip in clips:
        counts[clip.asset_id] = counts.get(clip.asset_id, 0) + 1
    return counts


def _mark_assets_ready(
    assets: list[AssetModel],
    clips: list[ClipModel],
    *,
    updated_at: str,
) -> list[AssetModel]:
    clip_counts = _asset_clip_counts(clips)
    return [
        asset.model_copy(
            update={
                "processing_stage": "ready" if clip_counts.get(asset.id, 0) > 0 else asset.processing_stage,
                "processing_progress": 100 if clip_counts.get(asset.id, 0) > 0 else asset.processing_progress,
                "clip_count": clip_counts.get(asset.id, 0),
                "indexed_clip_count": clip_counts.get(asset.id, 0),
                "last_error": None,
                "updated_at": updated_at,
            }
        )
        for asset in assets
    ]


def _build_clips(assets: list[AssetModel]) -> list[ClipModel]:
    clips: list[ClipModel] = []
    semantic_bank = [
        ["wide", "establishing", "environment"],
        ["action", "subject", "motion"],
        ["detail", "texture", "closeup"],
        ["transition", "reaction", "cutaway"],
    ]
    for asset_index, asset in enumerate(assets, start=1):
        for offset in range(2):
            clip_index = (asset_index - 1) * 2 + offset
            start_ms = offset * 6000
            end_ms = start_ms + 6000
            semantic_tags = semantic_bank[clip_index % len(semantic_bank)]
            clips.append(
                ClipModel(
                    id=_entity_id("clip"),
                    asset_id=asset.id,
                    source_start_ms=start_ms,
                    source_end_ms=end_ms,
                    visual_desc=f"{asset.name} candidate highlight {offset + 1}",
                    semantic_tags=semantic_tags,
                    confidence=round(0.92 - clip_index * 0.05, 2),
                    thumbnail_ref=f"thumb-gradient-{(clip_index % 4) + 1}",
                )
            )
    return clips


def _draft_from_payload(project_id: str, created_at: str, media: MediaReference | None) -> EditDraftModel:
    assets = _build_assets(media, updated_at=created_at) if media else []
    clips = _build_clips(assets)
    assets = _mark_assets_ready(assets, clips, updated_at=created_at)
    return EditDraftModel(
        id=_entity_id("draft"),
        project_id=project_id,
        version=1,
        status="draft",
        assets=assets,
        clips=clips,
        shots=[],
        scenes=None,
        selected_scene_id=None,
        selected_shot_id=None,
        created_at=created_at,
        updated_at=created_at,
    )


def _bump_draft(draft: EditDraftModel, **changes: Any) -> EditDraftModel:
    next_version = int(changes.pop("version", draft.version + 1))
    next_updated_at = str(changes.pop("updated_at", _now_iso()))
    return draft.model_copy(update={"version": next_version, "updated_at": next_updated_at, **changes})


def _build_edit_plan(clips: list[ClipModel], prompt: str) -> tuple[list[ShotModel], list[SceneModel]]:
    selected = clips[: min(3, len(clips))]
    base_prompt = _trimmed(prompt) or "Generate a tighter first cut"
    shot_labels = ["Open", "Lift", "Payoff"]
    shots: list[ShotModel] = []
    scenes: list[SceneModel] = []

    for index, clip in enumerate(selected):
        shot_duration_ms = min(clip.source_end_ms - clip.source_start_ms, 4000 + index * 1000)
        source_in_ms = clip.source_start_ms
        source_out_ms = source_in_ms + shot_duration_ms
        shot = ShotModel(
            id=_entity_id("shot"),
            clip_id=clip.id,
            source_in_ms=source_in_ms,
            source_out_ms=source_out_ms,
            order=index,
            enabled=True,
            label=shot_labels[index] if index < len(shot_labels) else f"Shot {index + 1}",
            intent=f"{base_prompt[:60]} | {clip.visual_desc}",
            note=None,
            locked_fields=[],
        )
        shots.append(shot)
        scenes.append(
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
        )

    return shots, scenes


def _draft_summary(draft: EditDraftModel) -> dict[str, Any]:
    return {
        "draft_id": draft.id,
        "draft_version": draft.version,
        "asset_count": len(draft.assets),
        "clip_count": len(draft.clips),
        "shot_count": len(draft.shots),
        "scene_count": len(draft.scenes or []),
        "selected_scene_id": draft.selected_scene_id,
        "selected_shot_id": draft.selected_shot_id,
        "clip_excerpt": [
            {
                "clip_id": clip.id,
                "asset_id": clip.asset_id,
                "visual_desc": clip.visual_desc,
                "semantic_tags": clip.semantic_tags,
            }
            for clip in draft.clips[:6]
        ],
    }


def _chat_history_summary(record: dict[str, Any], *, max_turns: int = 6) -> list[str]:
    lines: list[str] = []
    for turn in record["chat_turns"][-max_turns:]:
        if turn.get("role") == "user":
            lines.append(f"user: {str(turn.get('content', '')).strip()[:160]}")
            continue
        if turn.get("role") == "assistant":
            lines.append(f"assistant: {str(turn.get('reasoning_summary', '')).strip()[:160]}")
    return lines


def _extract_first_json_object(text: str) -> str | None:
    depth = 0
    start_index: int | None = None
    for index, char in enumerate(text):
        if char == "{":
            if start_index is None:
                start_index = index
            depth += 1
        elif char == "}":
            if start_index is None:
                continue
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    return None
