"""预览渲染工具 - 快速、低分辨率的预览生成"""
from __future__ import annotations

import time
from typing import Any

from app.tools.registry import ToolResult


class PreviewRendererTool:
    """预览渲染工具

    职责：
    1. 生成快速预览视频
    2. 使用低分辨率和快速编码
    3. 支持幂等（重复调用覆盖旧预览）
    """

    name = "render_preview"

    # 质量预设
    QUALITY_PRESETS = {
        "low": {"resolution": "480p", "bitrate": "1M"},
        "medium": {"resolution": "720p", "bitrate": "2M"},
        "high": {"resolution": "1080p", "bitrate": "4M"},
    }

    def run(
        self,
        timeline_json: dict[str, Any],
        *,
        quality: str = "low",
        output_format: str = "webm",
        project_id: str | None = None,
    ) -> ToolResult:
        """生成预览视频

        特点:
        - 快速编码（使用webm/vp9快速预设）
        - 低分辨率（480p或更低）
        - 可重复生成（幂等，每次覆盖旧预览）
        - 缓存在本地临时目录

        Args:
            timeline_json: 时间线数据
            quality: 质量等级（low/medium/high）
            output_format: 输出格式（默认webm）
            project_id: 项目ID（用于生成缓存路径）

        Returns:
            ToolResult with payload:
                - preview_url: str - 预览文件URL
                - render_type: str - "preview"
                - duration_ms: int - 视频时长
                - quality: str - 质量等级
                - format: str - 文件格式
        """
        try:
            # 获取项目ID
            pid = project_id or timeline_json.get("project_id", "default")

            # 获取质量预设
            preset = self.QUALITY_PRESETS.get(quality, self.QUALITY_PRESETS["low"])

            # 生成预览URL（幂等：固定路径，每次覆盖）
            # 实际实现会调用FFmpeg
            preview_url = f"file:///tmp/entrocut/preview/{pid}/latest.{output_format}"

            # Mock实现：模拟渲染耗时
            # 实际应该调用FFmpeg进行编码
            time.sleep(0.1)  # 模拟快速编码

            duration_ms = timeline_json.get("duration_ms", 0)

            return ToolResult(
                ok=True,
                payload={
                    "preview_url": preview_url,
                    "render_type": "preview",
                    "duration_ms": duration_ms,
                    "quality": quality,
                    "format": output_format,
                    "resolution": preset["resolution"],
                    "bitrate": preset["bitrate"],
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                payload={
                    "error": str(e),
                    "render_type": "preview",
                },
            )
