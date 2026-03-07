"""Ingest状态仓库 - 跟踪资产处理状态"""
from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    """返回当前UTC时间的ISO格式字符串"""
    return datetime.now(tz=UTC).isoformat()


class IngestStateRepository:
    """管理资产处理状态

    职责：
    1. 跟踪每个资产在各阶段的完成状态
    2. 提供状态查询和更新接口
    3. 支持增量处理的状态判断
    """

    def __init__(self, db_conn: sqlite3.Connection, lock: threading.Lock):
        """初始化状态仓库

        Args:
            db_conn: SQLite数据库连接
            lock: 线程锁，确保并发安全
        """
        self._db = db_conn
        self._lock = lock
        self._ensure_table()

    def _ensure_table(self) -> None:
        """确保ingest_state表存在"""
        with self._lock:
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_state (
                    state_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    scan_completed INTEGER DEFAULT 0,
                    segment_completed INTEGER DEFAULT 0,
                    frames_extracted INTEGER DEFAULT 0,
                    embedding_completed INTEGER DEFAULT 0,
                    indexed INTEGER DEFAULT 0,
                    preview_rendered INTEGER DEFAULT 0,
                    last_error TEXT,
                    last_processed_at TEXT,
                    UNIQUE(asset_id, project_id, user_id)
                )
                """
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingest_state_project "
                "ON ingest_state(project_id, user_id)"
            )
            self._db.commit()

    def get_pending_assets(
        self,
        project_id: str,
        user_id: str,
        *,
        phase: str = "segment",
        include_failed: bool = True,
    ) -> list[str]:
        """获取待处理（或失败）的资产ID列表

        Args:
            project_id: 项目ID
            user_id: 用户ID
            phase: 检查的阶段名称
            include_failed: 是否包含失败的资产

        Returns:
            资产ID列表
        """
        phase_column = self._phase_to_column(phase)
        if not phase_column:
            return []

        with self._lock:
            if include_failed:
                query = f"""
                    SELECT asset_id FROM ingest_state
                    WHERE project_id = ? AND user_id = ?
                    AND ({phase_column} = 0 OR last_error IS NOT NULL)
                """
            else:
                query = f"""
                    SELECT asset_id FROM ingest_state
                    WHERE project_id = ? AND user_id = ?
                    AND {phase_column} = 0
                """

            cursor = self._db.execute(query, (project_id, user_id))
            return [row[0] for row in cursor.fetchall()]

    def get_state(self, asset_id: str, project_id: str, user_id: str) -> dict[str, Any] | None:
        """获取资产的处理状态

        Args:
            asset_id: 资产ID
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            状态字典，不存在则返回None
        """
        with self._lock:
            cursor = self._db.execute(
                """
                SELECT asset_id, project_id, user_id,
                       scan_completed, segment_completed, frames_extracted,
                       embedding_completed, indexed, preview_rendered,
                       last_error, last_processed_at
                FROM ingest_state
                WHERE asset_id = ? AND project_id = ? AND user_id = ?
                """,
                (asset_id, project_id, user_id),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "asset_id": row[0],
                    "project_id": row[1],
                    "user_id": row[2],
                    "scan_completed": bool(row[3]),
                    "segment_completed": bool(row[4]),
                    "frames_extracted": bool(row[5]),
                    "embedding_completed": bool(row[6]),
                    "indexed": bool(row[7]),
                    "preview_rendered": bool(row[8]),
                    "last_error": row[9],
                    "last_processed_at": row[10],
                }
            return None

    def get_states_by_project(
        self, project_id: str, user_id: str
    ) -> dict[str, dict[str, Any]]:
        """获取项目下所有资产的状态

        Args:
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            asset_id -> 状态字典的映射
        """
        with self._lock:
            cursor = self._db.execute(
                """
                SELECT asset_id, project_id, user_id,
                       scan_completed, segment_completed, frames_extracted,
                       embedding_completed, indexed, preview_rendered,
                       last_error, last_processed_at
                FROM ingest_state
                WHERE project_id = ? AND user_id = ?
                """,
                (project_id, user_id),
            )
            return {
                row[0]: {
                    "asset_id": row[0],
                    "project_id": row[1],
                    "user_id": row[2],
                    "scan_completed": bool(row[3]),
                    "segment_completed": bool(row[4]),
                    "frames_extracted": bool(row[5]),
                    "embedding_completed": bool(row[6]),
                    "indexed": bool(row[7]),
                    "preview_rendered": bool(row[8]),
                    "last_error": row[9],
                    "last_processed_at": row[10],
                }
                for row in cursor.fetchall()
            }

    def mark_phase_completed(
        self,
        asset_id: str,
        project_id: str,
        user_id: str,
        phase: str,
    ) -> None:
        """标记某阶段完成

        Args:
            asset_id: 资产ID
            project_id: 项目ID
            user_id: 用户ID
            phase: 阶段名称
        """
        phase_column = self._phase_to_column(phase)
        if not phase_column:
            return

        state_id = f"{project_id}_{asset_id}"
        now = _now_iso()

        with self._lock:
            # 使用UPSERT语义
            self._db.execute(
                f"""
                INSERT INTO ingest_state (
                    state_id, asset_id, project_id, user_id,
                    {phase_column}, last_processed_at
                ) VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(asset_id, project_id, user_id)
                DO UPDATE SET {phase_column} = 1, last_processed_at = ?, last_error = NULL
                """,
                (state_id, asset_id, project_id, user_id, now, now),
            )
            self._db.commit()

    def mark_phase_failed(
        self,
        asset_id: str,
        project_id: str,
        user_id: str,
        phase: str,
        error: str,
    ) -> None:
        """标记某阶段失败

        Args:
            asset_id: 资产ID
            project_id: 项目ID
            user_id: 用户ID
            phase: 阶段名称
            error: 错误信息
        """
        phase_column = self._phase_to_column(phase)
        if not phase_column:
            return

        state_id = f"{project_id}_{asset_id}"
        now = _now_iso()

        with self._lock:
            self._db.execute(
                f"""
                INSERT INTO ingest_state (
                    state_id, asset_id, project_id, user_id,
                    last_error, last_processed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, project_id, user_id)
                DO UPDATE SET last_error = ?, last_processed_at = ?
                """,
                (state_id, asset_id, project_id, user_id, error, now, error, now),
            )
            self._db.commit()

    def reset_project(self, project_id: str, user_id: str) -> None:
        """重置项目的所有状态（用于全量重跑）

        Args:
            project_id: 项目ID
            user_id: 用户ID
        """
        with self._lock:
            self._db.execute(
                "DELETE FROM ingest_state WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            self._db.commit()

    def _phase_to_column(self, phase: str) -> str | None:
        """将阶段名称映射到数据库列名

        Args:
            phase: 阶段名称

        Returns:
            列名，无效阶段返回None
        """
        mapping = {
            "scan": "scan_completed",
            "segment": "segment_completed",
            "extract_frames": "frames_extracted",
            "embed": "embedding_completed",
            "index": "indexed",
            "render": "preview_rendered",
        }
        return mapping.get(phase)
