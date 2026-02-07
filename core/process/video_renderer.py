"""
本地视频渲染器

根据 EDL clips 调用 FFmpeg 进行剪辑拼接，输出最终视频。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List


class RenderError(Exception):
    """渲染异常。"""


class VideoRenderer:
    """FFmpeg 渲染器。"""

    def render(self, clips: List[Dict[str, Any]], output_path: str, work_dir: str) -> str:
        if not clips:
            raise RenderError("No clips to render")

        target = Path(output_path).expanduser().resolve()
        temp_dir = Path(work_dir).expanduser().resolve()
        segments_dir = temp_dir / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)

        segment_files = []
        for idx, clip in enumerate(clips):
            src = Path(str(clip["src"])).expanduser().resolve()
            start = float(clip["start"])
            end = float(clip["end"])
            if end <= start:
                raise RenderError(f"Invalid clip time range: start={start}, end={end}")
            if not src.exists() or not src.is_file():
                raise RenderError(f"Clip source not found: {src}")

            segment_path = segments_dir / f"segment_{idx:04d}.mp4"
            self._cut_segment(src, segment_path, start, end)
            segment_files.append(segment_path)

        concat_file = temp_dir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{segment_file.as_posix()}'\n" for segment_file in segment_files),
            encoding="utf-8",
        )
        self._concat_segments(concat_file, target)
        return str(target)

    @staticmethod
    def _cut_segment(src: Path, target: Path, start: float, end: float) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.6f}",
            "-to",
            f"{end:.6f}",
            "-i",
            str(src),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(target),
        ]
        VideoRenderer._run_command(cmd, "cut segment")

    @staticmethod
    def _concat_segments(concat_file: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ]
        VideoRenderer._run_command(cmd, "concat segments")

    @staticmethod
    def _run_command(command: List[str], action: str) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RenderError(f"FFmpeg failed to {action}: {exc.stderr}") from exc
