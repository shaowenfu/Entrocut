"""导出渲染工具 - 高质量的最终输出"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.tools.registry import ToolResult


class ExportRendererTool:
    """导出渲染工具

    职责：
    1. 生成高质量最终导出视频
    2. 使用原始分辨率或指定分辨率
    3. 每次生成新文件（不可变）
    4. 输出到用户指定位置
    """

    name = "render_export"

    # 分辨率预设
    RESOLUTION_PRESETS = {
        "original": None,  # 保持原始分辨率
        "1080p": "1920x1080",
        "720p": "1280x720",
        "480p": "854x480",
    }

    # 编码器预设
    CODEC_PRESETS = {
        "h264": {"codec": "libx264", "preset": "slow", "crf": "18"},
        "h265": {"codec": "libx265", "preset": "slow", "crf": "20"},
        "vp9": {"codec": "libvpx-vp9", "preset": "slow", "crf": "20"},
    }

    def run(
        self,
        timeline_json: dict[str, Any],
        *,
        format: str = "mp4",
        resolution: str = "original",
        codec: str = "h264",
        output_path: str | None = None,
        project_id: str | None = None,
    ) -> ToolResult:
        """生成最终导出视频

        特点:
        - 高质量编码
        - 原始分辨率或指定分辨率
        - 输出到用户指定位置
        - 生成唯一文件名（带时间戳）
        - 不可变（每次生成新文件）

        Args:
            timeline_json: 时间线数据
            format: 输出格式（默认mp4）
            resolution: 分辨率（original/1080p/720p）
            codec: 编码器（h264/h265/vp9）
            output_path: 用户指定的输出路径
            project_id: 项目ID

        Returns:
            ToolResult with payload:
                - export_url: str - 导出文件URL
                - render_type: str - "export"
                - duration_ms: int - 视频时长
                - file_size_bytes: int - 文件大小
                - format: str - 文件格式
                - resolution: str - 分辨率
                - timestamp: int - 时间戳
        """
        try:
            # 获取项目ID
            pid = project_id or timeline_json.get("project_id", "default")

            # 生成唯一文件名（带高精度时间戳）
            # 使用纳秒级时间避免在同一秒内重复导出时发生冲突。
            timestamp = time.time_ns()

            # 确定输出路径
            if output_path:
                # 使用用户指定的路径
                output_file = Path(output_path)
                if output_file.is_dir():
                    # 如果是目录，生成文件名
                    output_file = output_file / f"{pid}_{timestamp}.{format}"
            else:
                # 使用默认导出目录
                output_dir = Path.home() / "Videos" / "entrocut_exports"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{pid}_{timestamp}.{format}"

            # 获取分辨率预设
            resolution_value = self.RESOLUTION_PRESETS.get(resolution)

            # 获取编码器预设
            codec_preset = self.CODEC_PRESETS.get(codec, self.CODEC_PRESETS["h264"])

            # Mock实现：模拟渲染耗时
            # 实际应该调用FFmpeg高质量编码
            time.sleep(0.5)  # 模拟较慢的编码

            duration_ms = timeline_json.get("duration_ms", 0)

            # Mock文件大小（实际应该从FFmpeg输出获取）
            # 假设1080p H264是 8Mbps，根据时长估算
            bitrate_bps = 8_000_000  # 8 Mbps
            file_size_bytes = int((duration_ms / 1000) * (bitrate_bps / 8))

            return ToolResult(
                ok=True,
                payload={
                    "export_url": f"file://{output_file}",
                    "render_type": "export",
                    "duration_ms": duration_ms,
                    "file_size_bytes": file_size_bytes,
                    "format": format,
                    "resolution": resolution,
                    "codec": codec,
                    "timestamp": timestamp,
                    "output_path": str(output_file),
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                payload={
                    "error": str(e),
                    "render_type": "export",
                },
            )
