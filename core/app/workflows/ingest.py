"""Ingest工作流 - 协调媒体导入的各阶段处理"""
from __future__ import annotations

from typing import Any

from app.repositories.asset_repository import AssetRepository
from app.repositories.ingest_state_repository import IngestStateRepository
from app.schemas.ingest import IngestConfig, IngestMode
from app.tools.ingest_coordinator import IngestCoordinatorTool
from app.tools.media_scanner import MediaScannerTool
from app.workflows.launchpad import LaunchpadWorkflowShell


class IngestWorkflow:
    """Ingest工作流，协调各阶段处理

    职责：
    1. 扫描目录并去重
    2. 管理阶段化进度
    3. 协调各工具执行
    """

    def __init__(
        self,
        scanner: MediaScannerTool,
        coordinator: IngestCoordinatorTool,
        asset_repo: AssetRepository,
        state_repo: IngestStateRepository,
        launchpad: LaunchpadWorkflowShell,
    ):
        """初始化Ingest工作流

        Args:
            scanner: 媒体扫描工具
            coordinator: Ingest协调器
            asset_repo: 资产仓库
            state_repo: Ingest状态仓库
            launchpad: 启动台工作流（用于进度通知）
        """
        self._scanner = scanner
        self._coordinator = coordinator
        self._asset_repo = asset_repo
        self._state_repo = state_repo
        self._launchpad = launchpad

    async def scan_and_dedupe(
        self,
        project_id: str,
        user_id: str,
        folder_path: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """扫描并去重，返回新增资产

        保证幂等：重复扫描同一目录不会产生重复资产

        Args:
            project_id: 项目ID
            user_id: 用户ID
            folder_path: 要扫描的目录路径
            request_id: 请求ID（可选）

        Returns:
            扫描结果字典
        """
        # 1. 获取已存在的hash集合
        existing_hashes = self._asset_repo.get_existing_hashes(project_id, user_id)

        # 2. 扫描新文件
        scan_result = self._scanner.run(
            folder_path=folder_path,
            existing_hashes=existing_hashes,
        )

        # 3. 通知进度
        if scan_result.ok:
            payload = scan_result.payload
            await self._launchpad.notify_media_progress(
                project_id=project_id,
                stage="scan",
                progress=0.3,
                message=f"found_{payload['total_found']}_new_{len(payload['new_assets'])}",
                request_id=request_id,
            )

        return scan_result.payload

    async def report_progress(
        self,
        project_id: str,
        action: str,
        **kwargs: Any,
    ) -> None:
        """统一进度上报

        Args:
            project_id: 项目ID
            action: 协调器动作
            **kwargs: 动作参数
        """
        result = self._coordinator.run(action, **kwargs)
        if result.ok:
            payload = result.payload
            current_phase = payload.get("current_phase")

            if current_phase:
                await self._launchpad.notify_media_progress(
                    project_id=project_id,
                    stage=current_phase,
                    progress=payload.get("overall_progress", 0.0),
                    message=f"phase_{current_phase}_progress_{payload.get('overall_progress', 0.0):.2%}",
                    request_id=kwargs.get("request_id"),
                )

    async def run_phased_ingest(
        self,
        project_id: str,
        user_id: str,
        folder_path: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """运行阶段化ingest流程

        Args:
            project_id: 项目ID
            user_id: 用户ID
            folder_path: 要扫描的目录路径
            request_id: 请求ID（可选）

        Returns:
            最终进度信息
        """
        # 重置协调器
        self._coordinator.run("reset")

        # Phase 1: SCAN
        await self.report_progress(
            project_id, "start_phase", phase="scan", total_items=1, request_id=request_id
        )

        scan_result = await self.scan_and_dedupe(project_id, user_id, folder_path, request_id=request_id)

        await self.report_progress(project_id, "complete_phase", phase="scan", request_id=request_id)

        new_assets = scan_result.get("new_assets", [])

        # Phase 2: SEGMENT (mock实现)
        await self.report_progress(
            project_id,
            "start_phase",
            phase="segment",
            total_items=len(new_assets),
            request_id=request_id,
        )

        for i, asset in enumerate(new_assets):
            # 这里应该调用真实的segmentation工具
            # 当前是mock实现
            await self.report_progress(
                project_id,
                "update_progress",
                phase="segment",
                items_processed=i + 1,
                request_id=request_id,
            )

        await self.report_progress(project_id, "complete_phase", phase="segment", request_id=request_id)

        # Phase 3: EXTRACT_FRAMES (mock实现)
        await self.report_progress(
            project_id,
            "start_phase",
            phase="extract_frames",
            total_items=len(new_assets),
            request_id=request_id,
        )

        for i, asset in enumerate(new_assets):
            # 这里应该调用真实的frame extraction工具
            # 当前是mock实现
            await self.report_progress(
                project_id,
                "update_progress",
                phase="extract_frames",
                items_processed=i + 1,
                request_id=request_id,
            )

        await self.report_progress(
            project_id, "complete_phase", phase="extract_frames", request_id=request_id
        )

        # Phase 4-6: EMBED, INDEX, RENDER (简化实现)
        for phase in ["embed", "index", "render"]:
            await self.report_progress(project_id, "start_phase", phase=phase, total_items=1, request_id=request_id)
            await self.report_progress(project_id, "complete_phase", phase=phase, request_id=request_id)

        # 获取最终进度
        final_progress = self._coordinator.run("get_overall_progress")
        return final_progress.payload

    async def run(
        self,
        project_id: str,
        user_id: str,
        folder_path: str,
        *,
        config: IngestConfig | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """统一入口，根据mode选择策略

        Args:
            project_id: 项目ID
            user_id: 用户ID
            folder_path: 要扫描的目录路径
            config: Ingest配置（可选）
            request_id: 请求ID（可选）

        Returns:
            最终进度信息
        """
        config = config or IngestConfig()

        if config.mode == IngestMode.FULL:
            return await self._run_full_ingest(project_id, user_id, folder_path, config, request_id)
        else:
            return await self._run_incremental_ingest(project_id, user_id, folder_path, config, request_id)

    async def _run_incremental_ingest(
        self,
        project_id: str,
        user_id: str,
        folder_path: str,
        config: IngestConfig,
        request_id: str | None,
    ) -> dict[str, Any]:
        """增量处理：只处理新增和失败的资产

        Args:
            project_id: 项目ID
            user_id: 用户ID
            folder_path: 要扫描的目录路径
            config: Ingest配置
            request_id: 请求ID

        Returns:
            最终进度信息
        """
        # 1. 扫描新文件
        scan_result = await self.scan_and_dedupe(project_id, user_id, folder_path, request_id=request_id)
        new_assets = scan_result.get("new_assets", [])

        # 2. 获取已存在资产的状态
        states = self._state_repo.get_states_by_project(project_id, user_id)

        # 3. 筛选待处理资产
        pending_assets = []
        for asset in new_assets:
            pending_assets.append(asset)  # 新资产都需要处理

        # 4. 如果配置了重新处理失败，添加失败的资产
        if config.reprocess_failed:
            all_assets = self._asset_repo.list_assets_by_project(project_id, user_id)
            for asset in all_assets:
                state = states.get(asset["asset_id"])
                if state and state.get("last_error"):
                    pending_assets.append(asset)

        # 5. 执行处理
        if pending_assets:
            # 使用现有的阶段化处理逻辑
            # 这里简化为直接调用run_phased_ingest
            # 实际应该只处理pending_assets
            return await self.run_phased_ingest(project_id, user_id, folder_path, request_id=request_id)
        else:
            # 没有待处理资产
            return {"overall_progress": 1.0, "message": "no_pending_assets"}

    async def _run_full_ingest(
        self,
        project_id: str,
        user_id: str,
        folder_path: str,
        config: IngestConfig,
        request_id: str | None,
    ) -> dict[str, Any]:
        """全量重跑：重新处理所有资产

        Args:
            project_id: 项目ID
            user_id: 用户ID
            folder_path: 要扫描的目录路径
            config: Ingest配置
            request_id: 请求ID

        Returns:
            最终进度信息
        """
        # 1. 重置所有状态
        self._state_repo.reset_project(project_id, user_id)

        # 2. 执行全量处理
        return await self.run_phased_ingest(project_id, user_id, folder_path, request_id=request_id)

