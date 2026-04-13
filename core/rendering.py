from __future__ import annotations

import subprocess
from pathlib import Path

from helpers import _entity_id
from schemas import CoreApiError, EditDraftModel, RenderPlan, RenderSegment


def build_render_plan(draft: EditDraftModel) -> RenderPlan:
    clips_by_id = {clip.id: clip for clip in draft.clips}
    assets_by_id = {asset.id: asset for asset in draft.assets}
    scenes = draft.scenes or []
    scene_by_shot_id = {shot_id: scene.id for scene in scenes for shot_id in scene.shot_ids}

    segments: list[RenderSegment] = []
    for shot in sorted(draft.shots, key=lambda item: item.order):
        clip = clips_by_id.get(shot.clip_id)
        if clip is None:
            raise CoreApiError(status_code=422, code="RENDER_CLIP_NOT_FOUND", message=f"Shot {shot.id} clip is missing.")
        asset = assets_by_id.get(clip.asset_id)
        if asset is None or not asset.source_path:
            raise CoreApiError(status_code=422, code="RENDER_ASSET_PATH_MISSING", message=f"Asset path missing for shot {shot.id}.")
        if shot.source_in_ms >= shot.source_out_ms:
            raise CoreApiError(status_code=422, code="RENDER_INVALID_RANGE", message=f"Shot {shot.id} has invalid range.")
        segments.append(
            RenderSegment(
                asset_id=asset.id,
                source_path=asset.source_path,
                source_in_ms=shot.source_in_ms,
                source_out_ms=shot.source_out_ms,
                shot_id=shot.id,
                scene_id=scene_by_shot_id.get(shot.id),
                order=shot.order,
            )
        )

    return RenderPlan(
        project_id=draft.project_id,
        draft_id=draft.id,
        draft_version=draft.version,
        segments=segments,
        estimated_duration_ms=sum(seg.source_out_ms - seg.source_in_ms for seg in segments),
    )


def _run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise CoreApiError(status_code=500, code="FFMPEG_NOT_FOUND", message="ffmpeg is required for rendering.") from exc
    except subprocess.CalledProcessError as exc:
        raise CoreApiError(
            status_code=500,
            code="RENDER_FFMPEG_FAILED",
            message="ffmpeg rendering failed.",
            details={"stderr": exc.stderr.decode("utf-8", errors="ignore")[:400]},
        ) from exc


def _render_from_plan(plan: RenderPlan, output_path: Path, *, quality: str) -> dict[str, int | str]:
    if not plan.segments:
        raise CoreApiError(status_code=409, code="RENDER_PLAN_EMPTY", message="Draft has no renderable segments.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output_path.parent / f"tmp_{_entity_id('render')}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    segment_files: list[Path] = []
    for idx, segment in enumerate(plan.segments):
        segment_file = temp_dir / f"segment_{idx:03d}.mp4"
        duration_sec = max(0.05, (segment.source_out_ms - segment.source_in_ms) / 1000)
        ss = max(0, segment.source_in_ms / 1000)
        source = Path(segment.source_path)
        if source.exists():
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{ss:.3f}",
                    "-t",
                    f"{duration_sec:.3f}",
                    "-i",
                    segment.source_path,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast" if quality == "preview" else "medium",
                    "-crf",
                    "30" if quality == "preview" else "22",
                    "-an",
                    str(segment_file),
                ]
            )
        else:
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black:s=640x360:d={duration_sec:.3f}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-an",
                    str(segment_file),
                ]
            )
        segment_files.append(segment_file)

    concat_file = temp_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{file.as_posix()}'" for file in segment_files), encoding="utf-8")
    _run_ffmpeg([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(output_path),
    ])

    for file in segment_files:
        file.unlink(missing_ok=True)
    concat_file.unlink(missing_ok=True)
    temp_dir.rmdir()

    return {
        "output_url": output_path.resolve().as_uri(),
        "duration_ms": plan.estimated_duration_ms,
        "file_size_bytes": output_path.stat().st_size if output_path.exists() else 0,
    }


def render_preview(plan: RenderPlan, output_path: Path) -> dict[str, int | str]:
    return _render_from_plan(plan, output_path, quality="preview")


def render_export(plan: RenderPlan, output_path: Path, *, quality: str | None = None) -> dict[str, int | str]:
    return _render_from_plan(plan, output_path, quality=quality or "export")
