"""
帧抽取器 - 使用 FFmpeg

从视频中按场景抽取关键帧。
"""

from typing import List
from dataclasses import dataclass


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

    def extract(self, video_path: str, scenes: List, frames_per_scene: int = 3) -> ExtractResult:
        """
        从视频中抽取帧

        Args:
            video_path: 视频文件路径
            scenes: 场景片段列表
            frames_per_scene: 每个场景抽取的帧数

        Returns:
            ExtractResult: 包含所有提取的帧信息
        """
        # TODO: 集成 FFmpeg
        # 使用 ffmpeg-python 或 subprocess 调用 FFmpeg

        # 临时返回空结果用于测试
        return ExtractResult(
            video_path=video_path,
            extracted_frames=[]
        )
