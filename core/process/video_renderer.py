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
        # 修复 moov 原子位置：浏览器需要 moov 在文件开头才能流式播放
        self._fix_moov_atom(target)
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

    @staticmethod
    def _fix_moov_atom(video_path: Path) -> None:
        """将 moov 原子移到文件开头，使视频可流式播放。

        concat 使用 -c copy 不会重新排列 moov 原子，导致 moov 在文件末尾。
        浏览器需要 moov 在开头才能解析并播放视频。
        """
        temp_output = video_path.with_suffix('.tmp.mp4')
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-c", "copy",           # 不重新编码，只重新排列原子
            "-movflags", "+faststart",  # 将 moov 移到文件开头
            str(temp_output),
        ]
        VideoRenderer._run_command(cmd, "fix moov atom")
        # 替换原文件
        temp_output.replace(video_path)
