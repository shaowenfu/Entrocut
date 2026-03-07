"""Ingest协调器 - 管理多阶段进度跟踪"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.tools.registry import ToolResult


class IngestPhase(str, Enum):
    """Ingest处理阶段"""

    SCAN = "scan"
    SEGMENT = "segment"
    EXTRACT_FRAMES = "extract_frames"
    EMBED = "embed"
    INDEX = "index"
    RENDER = "render"


@dataclass
class PhaseProgress:
    """单个阶段的进度信息"""

    phase: IngestPhase
    weight: float  # 在总进度中的权重
    status: str = "pending"  # pending/running/completed/failed
    progress: float = 0.0  # 0.0-1.0
    items_processed: int = 0
    items_total: int = 0


class IngestCoordinatorTool:
    """Ingest协调器，管理多阶段进度

    职责：
    1. 跟踪各个处理阶段的进度
    2. 计算总体进度
    3. 提供进度查询接口
    """

    name = "ingest_coordinator"

    # 各阶段权重（总和为1.0）
    PHASE_WEIGHTS = {
        IngestPhase.SCAN: 0.05,
        IngestPhase.SEGMENT: 0.25,
        IngestPhase.EXTRACT_FRAMES: 0.20,
        IngestPhase.EMBED: 0.25,
        IngestPhase.INDEX: 0.15,
        IngestPhase.RENDER: 0.10,
    }

    def __init__(self) -> None:
        """初始化协调器"""
        self._phases: dict[IngestPhase, PhaseProgress] = {
            phase: PhaseProgress(phase=phase, weight=weight)
            for phase, weight in self.PHASE_WEIGHTS.items()
        }
        self._current_phase: IngestPhase | None = None

    def run(self, action: str, **kwargs: Any) -> ToolResult:
        """执行协调器动作

        Actions:
        - start_phase: phase, total_items
        - update_progress: phase, items_processed
        - complete_phase: phase
        - fail_phase: phase, error
        - get_overall_progress: 返回总体进度
        - reset: 重置所有阶段状态

        Args:
            action: 动作名称
            **kwargs: 动作参数

        Returns:
            ToolResult包含进度信息
        """
        if action == "start_phase":
            return self._start_phase(kwargs["phase"], kwargs.get("total_items", 0))
        elif action == "update_progress":
            return self._update_progress(kwargs["phase"], kwargs["items_processed"])
        elif action == "complete_phase":
            return self._complete_phase(kwargs["phase"])
        elif action == "fail_phase":
            return self._fail_phase(kwargs["phase"], kwargs.get("error", "unknown"))
        elif action == "get_overall_progress":
            return self._get_overall_progress()
        elif action == "reset":
            return self._reset()
        else:
            return ToolResult(ok=False, payload={"error": f"unknown_action:{action}"})

    def _start_phase(self, phase: str, total_items: int) -> ToolResult:
        """开始一个阶段

        Args:
            phase: 阶段名称
            total_items: 该阶段要处理的总项目数

        Returns:
            ToolResult包含更新后的进度
        """
        try:
            p = IngestPhase(phase)
            self._phases[p].status = "running"
            self._phases[p].items_total = total_items
            self._current_phase = p
            return self._get_overall_progress()
        except ValueError:
            return ToolResult(ok=False, payload={"error": f"invalid_phase:{phase}"})

    def _update_progress(self, phase: str, items_processed: int) -> ToolResult:
        """更新阶段进度

        Args:
            phase: 阶段名称
            items_processed: 已处理的项目数

        Returns:
            ToolResult包含更新后的进度
        """
        try:
            p = IngestPhase(phase)
            pp = self._phases[p]
            pp.items_processed = items_processed
            if pp.items_total > 0:
                pp.progress = min(1.0, items_processed / pp.items_total)
            return self._get_overall_progress()
        except ValueError:
            return ToolResult(ok=False, payload={"error": f"invalid_phase:{phase}"})

    def _complete_phase(self, phase: str) -> ToolResult:
        """完成一个阶段

        Args:
            phase: 阶段名称

        Returns:
            ToolResult包含更新后的进度
        """
        try:
            p = IngestPhase(phase)
            self._phases[p].status = "completed"
            self._phases[p].progress = 1.0
            return self._get_overall_progress()
        except ValueError:
            return ToolResult(ok=False, payload={"error": f"invalid_phase:{phase}"})

    def _fail_phase(self, phase: str, error: str) -> ToolResult:
        """标记阶段失败

        Args:
            phase: 阶段名称
            error: 错误信息

        Returns:
            ToolResult包含失败信息
        """
        try:
            p = IngestPhase(phase)
            self._phases[p].status = "failed"
            return ToolResult(
                ok=False,
                payload={
                    "phase": phase,
                    "error": error,
                    **self._get_overall_progress().payload,
                },
            )
        except ValueError:
            return ToolResult(ok=False, payload={"error": f"invalid_phase:{phase}"})

    def _get_overall_progress(self) -> ToolResult:
        """计算总体进度

        Returns:
            ToolResult包含总体进度和各阶段状态
        """
        overall = 0.0
        phase_stats: dict[str, Any] = {}

        for phase, pp in self._phases.items():
            phase_stats[phase.value] = {
                "status": pp.status,
                "progress": pp.progress,
                "items_processed": pp.items_processed,
                "items_total": pp.items_total,
            }

            if pp.status == "completed":
                overall += pp.weight
            elif pp.status == "running":
                overall += pp.weight * pp.progress

        return ToolResult(
            ok=True,
            payload={
                "overall_progress": overall,
                "current_phase": self._current_phase.value if self._current_phase else None,
                "phase_stats": phase_stats,
            },
        )

    def _reset(self) -> ToolResult:
        """重置所有阶段状态

        Returns:
            ToolResult包含重置后的状态
        """
        for phase in self._phases:
            self._phases[phase].status = "pending"
            self._phases[phase].progress = 0.0
            self._phases[phase].items_processed = 0
            self._phases[phase].items_total = 0
        self._current_phase = None
        return self._get_overall_progress()
