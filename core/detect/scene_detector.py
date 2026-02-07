"""
场景检测器 - 使用 PySceneDetect

检测视频中的场景切换点（scene boundaries）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import cv2
from scenedetect import ContentDetector, detect


@dataclass
class SceneSegment:
    """场景片段"""

    start_frame: int
    end_frame: int
    start_time: float  # 秒
    end_time: float  # 秒


@dataclass
class DetectResult:
    """场景检测结果"""

    total_frames: int
    fps: float
    duration: float
    scenes: List[SceneSegment]


class SceneDetector:
    """
    场景检测器

    使用 PySceneDetect 的 ContentDetector 检测场景切换。
    """

    def __init__(self, threshold: float = 27.0, min_scene_length: int = 15):
        """
        初始化检测器

        Args:
            threshold: 检测阈值，越小越敏感
            min_scene_length: 最小场景长度（帧数）
        """
        self.threshold = threshold
        self.min_scene_length = min_scene_length

    def detect(self, video_path: str) -> DetectResult:
        """
        检测视频场景

        Args:
            video_path: 视频文件路径

        Returns:
            DetectResult: 包含所有检测到的场景片段
        """
        path = Path(video_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        fps, total_frames, duration = self._read_video_meta(path)
        raw_scenes = detect(
            str(path),
            ContentDetector(
                threshold=self.threshold,
                min_scene_len=self.min_scene_length,
            ),
        )
        scenes = [self._to_scene_segment(start, end) for start, end in raw_scenes]

        # 若未检测出切点，回退为一个全片场景，保证下游可继续执行。
        if not scenes and total_frames > 0 and duration > 0:
            scenes = [
                SceneSegment(
                    start_frame=0,
                    end_frame=total_frames,
                    start_time=0.0,
                    end_time=duration,
                )
            ]

        return DetectResult(
            total_frames=total_frames,
            fps=fps,
            duration=duration,
            scenes=scenes,
        )

    @staticmethod
    def _to_scene_segment(start, end) -> SceneSegment:
        return SceneSegment(
            start_frame=int(start.get_frames()),
            end_frame=int(end.get_frames()),
            start_time=float(start.get_seconds()),
            end_time=float(end.get_seconds()),
        )

    @staticmethod
    def _read_video_meta(video_path: Path) -> tuple[float, int, float]:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Unable to open video file: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        capture.release()

        if fps <= 0:
            fps = 30.0
        duration = (total_frames / fps) if total_frames > 0 else 0.0
        return fps, total_frames, duration
