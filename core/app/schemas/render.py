"""渲染配置与结果Schema"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class RenderType(str, Enum):
    """渲染类型"""

    PREVIEW = "preview"  # 快速预览，低分辨率
    EXPORT = "export"  # 最终导出，原始分辨率


class RenderJobPayload(BaseModel):
    """渲染任务负载"""

    project_id: str
    render_type: RenderType
    timeline_json: dict[str, Any]  # 时间线数据

    # Preview专用配置
    preview_quality: str = "low"  # low/medium/high
    preview_format: str = "webm"  # 快速编码格式

    # Export专用配置
    export_format: str = "mp4"
    export_resolution: str = "original"  # 1080p/720p/original
    export_codec: str = "h264"
    output_path: str | None = None  # 用户指定的输出路径


class RenderResultPayload(BaseModel):
    """渲染结果"""

    job_id: str
    render_type: RenderType
    output_url: str  # 输出文件URL
    duration_ms: int  # 视频时长（毫秒）
    file_size_bytes: int | None = None  # 文件大小（字节）
    thumbnail_url: str | None = None  # 缩略图URL
    format: str  # 文件格式
    quality: str | None = None  # 质量等级（仅预览）
    resolution: str | None = None  # 分辨率（仅导出）
