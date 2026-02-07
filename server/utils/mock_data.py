"""
Mock 数据生成器

实现固定输入固定输出的 Mock 数据生成逻辑
"""

from typing import List
from models.schemas import (
    SegmentInfo, AnalysisData, ClipInfo, EDLData
)


# ============================================
# Mock Analyze Data Generator
# ============================================

def generate_mock_analysis(
    job_id: str,
    video_path: str,
    frames_count: int
) -> AnalysisData:
    """
    生成 Mock 分析数据

    Args:
        job_id: 任务编号
        video_path: 视频路径
        frames_count: 帧数量

    Returns:
        AnalysisData: 分析结果数据
    """
    # 根据帧数量生成片段数量（每 4 帧一个片段）
    segment_count = max(1, frames_count // 4)

    segments: List[SegmentInfo] = []
    for i in range(segment_count):
        start = i * 10.0
        end = start + 10.0

        segments.append(SegmentInfo(
            segment_id=f"seg_{i:03d}",
            start_time=start,
            end_time=end,
            tags=["mock_tag", f"segment_{i}"],
            score=0.85,
            description=f"Mock analysis result for segment {i}"
        ))

    return AnalysisData(segments=segments)


# ============================================
# Mock EDL Data Generator
# ============================================

def generate_mock_edl(
    job_id: str,
    segments: List,
    video_path: str,
    rule: str = "highlight_first"
) -> EDLData:
    """
    生成 Mock EDL 数据

    Args:
        job_id: 任务编号
        segments: 片段列表
        video_path: 视频路径
        rule: 剪辑规则

    Returns:
        EDLData: EDL 数据
    """
    # 根据 rule 选择片段
    if rule == "highlight_first":
        # 选择前 3 个片段
        selected_segments = segments[:3]
    else:
        # 默认选择所有片段
        selected_segments = segments

    clips: List[ClipInfo] = []
    total_duration = 0.0

    for i, seg in enumerate(selected_segments):
        start = seg.start_time if hasattr(seg, 'start_time') else seg.get('start_time', 0.0)
        end = seg.end_time if hasattr(seg, 'end_time') else seg.get('end_time', 10.0)

        clips.append(ClipInfo(
            clip_id=f"clip_{i:03d}",
            src=video_path,
            start=start,
            end=end
        ))
        total_duration += (end - start)

    return EDLData(
        clips=clips,
        output_name="final.mp4",
        total_duration=total_duration
    )
