"""渲染工作流 - 协调预览和导出渲染"""
from __future__ import annotations

from typing import Any

from app.tools.export_renderer import ExportRendererTool
from app.tools.preview_renderer import PreviewRendererTool
from app.workflows.launchpad import LaunchpadWorkflowShell


class RenderWorkflow:
    """渲染工作流

    职责：
    1. 协调预览渲染（快速、可覆盖）
    2. 协调导出渲染（高质量、不可变）
    3. 管理渲染进度通知
    """

    def __init__(
        self,
        preview_renderer: PreviewRendererTool,
        export_renderer: ExportRendererTool,
        launchpad: LaunchpadWorkflowShell,
    ):
        """初始化渲染工作流

        Args:
            preview_renderer: 预览渲染工具
            export_renderer: 导出渲染工具
            launchpad: 启动台工作流（用于进度通知）
        """
        self._preview = preview_renderer
        self._export = export_renderer
        self._launchpad = launchpad

    async def render_preview(
        self,
        project_id: str,
        timeline_json: dict[str, Any],
        *,
        quality: str = "low",
        format: str = "webm",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """生成/更新预览

        特点:
        - 幂等：重复调用会覆盖旧预览
        - 快速：低分辨率
        - 实时：用户编辑时频繁调用

        Args:
            project_id: 项目ID
            timeline_json: 时间线数据
            quality: 质量等级（low/medium/high）
            format: 输出格式（默认webm）
            request_id: 请求ID（可选）

        Returns:
            渲染结果字典
        """
        # 通知开始
        await self._launchpad.notify_media_progress(
            project_id=project_id,
            stage="render",
            progress=0.0,
            message="preview_started",
            request_id=request_id,
        )

        # 执行渲染
        result = self._preview.run(
            timeline_json=timeline_json,
            quality=quality,
            output_format=format,
            project_id=project_id,
        )

        # 通知完成
        if result.ok:
            await self._launchpad.notify_media_progress(
                project_id=project_id,
                stage="render",
                progress=1.0,
                message="preview_completed",
                request_id=request_id,
            )
        else:
            await self._launchpad.notify_media_progress(
                project_id=project_id,
                stage="render",
                progress=0.0,
                message=f"preview_failed:{result.payload.get('error', 'unknown')}",
                request_id=request_id,
            )

        return result.payload

    async def render_export(
        self,
        project_id: str,
        timeline_json: dict[str, Any],
        *,
        format: str = "mp4",
        resolution: str = "original",
        codec: str = "h264",
        output_path: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """最终导出

        特点:
        - 不可变：每次生成新文件
        - 高质量：原始分辨率
        - 异步：可能耗时较长

        Args:
            project_id: 项目ID
            timeline_json: 时间线数据
            format: 输出格式（默认mp4）
            resolution: 分辨率（original/1080p/720p）
            codec: 编码器（h264/h265/vp9）
            output_path: 用户指定的输出路径
            request_id: 请求ID（可选）

        Returns:
            渲染结果字典
        """
        # 通知开始
        await self._launchpad.notify_media_progress(
            project_id=project_id,
            stage="render",
            progress=0.0,
            message="export_started",
            request_id=request_id,
        )

        # 执行渲染
        result = self._export.run(
            timeline_json=timeline_json,
            format=format,
            resolution=resolution,
            codec=codec,
            output_path=output_path,
            project_id=project_id,
        )

        # 通知完成
        if result.ok:
            export_url = result.payload.get("export_url", "")
            await self._launchpad.notify_media_progress(
                project_id=project_id,
                stage="render",
                progress=1.0,
                message=f"export_completed:{export_url}",
                request_id=request_id,
            )
        else:
            await self._launchpad.notify_media_progress(
                project_id=project_id,
                stage="render",
                progress=0.0,
                message=f"export_failed:{result.payload.get('error', 'unknown')}",
                request_id=request_id,
            )

        return result.payload

    async def render(
        self,
        project_id: str,
        timeline_json: dict[str, Any],
        *,
        render_type: str = "preview",
        request_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """统一渲染入口

        Args:
            project_id: 项目ID
            timeline_json: 时间线数据
            render_type: 渲染类型（preview/export）
            request_id: 请求ID（可选）
            **kwargs: 其他参数

        Returns:
            渲染结果字典
        """
        if render_type == "export":
            return await self.render_export(
                project_id=project_id,
                timeline_json=timeline_json,
                request_id=request_id,
                **kwargs,
            )
        else:
            return await self.render_preview(
                project_id=project_id,
                timeline_json=timeline_json,
                request_id=request_id,
                **kwargs,
            )
