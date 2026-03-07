"""Ingest配置与状态Schema"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class IngestMode(str, Enum):
    """Ingest处理模式"""

    INCREMENTAL = "incremental"  # 只处理新增资产
    FULL = "full"  # 全量重新处理


class IngestConfig(BaseModel):
    """Ingest配置"""

    mode: IngestMode = IngestMode.INCREMENTAL
    force_rescan: bool = False  # 强制重扫（忽略缓存的扫描结果）
    reprocess_failed: bool = True  # 重新处理之前失败的资产
    skip_phases: list[str] = []  # 跳过的阶段（如已做过索引）


class AssetIngestState(BaseModel):
    """单个资产的Ingest状态"""

    asset_id: str
    project_id: str
    user_id: str

    # 各阶段完成状态
    scan_completed: bool = False
    segment_completed: bool = False
    frames_extracted: bool = False
    embedding_completed: bool = False
    indexed: bool = False
    preview_rendered: bool = False

    # 错误信息
    last_error: str | None = None
    last_processed_at: str | None = None
