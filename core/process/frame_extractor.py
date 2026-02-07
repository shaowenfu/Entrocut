"""
帧抽取器 - 使用 FFmpeg

从视频中按场景抽取关键帧。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

import cv2


@dataclass
class ExtractedFrame:
    """提取的帧"""

    scene_index: int
    frame_number: int
    timestamp: float
    file_path: str


@dataclass
class ExtractResult:
    """抽帧结果"""

    video_path: str
    extracted_frames: List[ExtractedFrame]


class FrameExtractor:
    """
    帧抽取器

    使用 FFmpeg 从视频中抽取指定时间点的帧。
    """

    def extract(
        self,
        video_path: str,
        scenes: List,
        frames_per_scene: int = 3,
        output_dir: str | None = None,
    ) -> ExtractResult:
        """
        从视频中抽取帧

        Args:
            video_path: 视频文件路径
            scenes: 场景片段列表
            frames_per_scene: 每个场景抽取的帧数
            output_dir: 抽帧输出目录，未传时使用临时默认目录

        Returns:
            ExtractResult: 包含所有提取的帧信息
        """
        if frames_per_scene <= 0:
            raise ValueError("frames_per_scene must be greater than 0")

        source = Path(video_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        target_dir = self._resolve_output_dir(source, output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        fps = self._read_fps(source)
        normalized_scenes = self._normalize_scenes(scenes)

        extracted_frames: List[ExtractedFrame] = []
        for scene_index, scene in enumerate(normalized_scenes):
            timestamps = self._sample_timestamps(
                scene["start_time"],
                scene["end_time"],
                frames_per_scene,
            )
            for sample_index, timestamp in enumerate(timestamps):
                frame_file = (
                    target_dir
                    / f"scene_{scene_index:04d}_frame_{sample_index:02d}_{int(timestamp * 1000):010d}.jpg"
                )
                self._extract_single_frame(source, frame_file, timestamp)
                extracted_frames.append(
                    ExtractedFrame(
                        scene_index=scene_index,
                        frame_number=int(round(timestamp * fps)),
                        timestamp=round(timestamp, 6),
                        file_path=str(frame_file),
                    )
                )

        return ExtractResult(video_path=str(source), extracted_frames=extracted_frames)

    @staticmethod
    def _resolve_output_dir(source: Path, output_dir: str | None) -> Path:
        if output_dir:
            return Path(output_dir).expanduser().resolve()
        return source.parent / f"{source.stem}_frames"

    @staticmethod
    def _read_fps(video_path: Path) -> float:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Unable to open video file: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        capture.release()
        return fps if fps > 0 else 30.0

    @staticmethod
    def _normalize_scenes(scenes: List) -> List[dict]:
        normalized = []
        for scene in scenes:
            if isinstance(scene, dict):
                start_time = float(scene["start_time"])
                end_time = float(scene["end_time"])
            else:
                start_time = float(getattr(scene, "start_time"))
                end_time = float(getattr(scene, "end_time"))

            if end_time <= start_time:
                continue
            normalized.append({"start_time": start_time, "end_time": end_time})
        return normalized

    @staticmethod
    def _sample_timestamps(start_time: float, end_time: float, count: int) -> List[float]:
        duration = end_time - start_time
        if duration <= 0:
            return []

        if count == 1:
            return [start_time + duration / 2.0]

        return [start_time + duration * ((idx + 1) / (count + 1)) for idx in range(count)]

    @staticmethod
    def _extract_single_frame(video_path: Path, output_path: Path, timestamp: float) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.6f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Failed to extract frame at {timestamp:.3f}s: {exc.stderr}") from exc
