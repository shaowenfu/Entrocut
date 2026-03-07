"""资产数据访问层 - 封装资产相关的数据库操作"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    """返回当前UTC时间的ISO格式字符串"""
    return datetime.now(tz=UTC).isoformat()


@dataclass(slots=True)
class AssetRecord:
    """资产记录"""

    asset_id: str
    project_id: str
    user_id: str
    name: str
    duration_ms: int
    type: str  # "video" | "audio"
    source_path: str
    source_hash: str
    normalized_path: str | None = None


class AssetRepository:
    """资产仓库，封装所有资产相关的数据库操作

    职责：
    1. 管理资产的CRUD操作
    2. 提供去重查询接口
    3. 确保线程安全
    """

    def __init__(self, db_conn: sqlite3.Connection, lock: threading.Lock):
        """初始化资产仓库

        Args:
            db_conn: SQLite数据库连接
            lock: 线程锁，确保并发安全
        """
        self._db = db_conn
        self._lock = lock

    def get_existing_hashes(self, project_id: str, user_id: str) -> set[str]:
        """获取项目下所有已存在的source_hash

        Args:
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            source_hash集合
        """
        with self._lock:
            cursor = self._db.execute(
                "SELECT source_hash FROM assets WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            return {row[0] for row in cursor.fetchall()}

    def insert_asset(self, asset: AssetRecord) -> bool:
        """插入资产，利用UNIQUE约束保证幂等

        Args:
            asset: 资产记录

        Returns:
            True表示新插入，False表示已存在（UNIQUE约束冲突）
        """
        with self._lock:
            try:
                self._db.execute(
                    """
                    INSERT INTO assets (
                        asset_id, project_id, user_id, name, duration_ms, type,
                        source_path, source_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset.asset_id,
                        asset.project_id,
                        asset.user_id,
                        asset.name,
                        asset.duration_ms,
                        asset.type,
                        asset.source_path,
                        asset.source_hash,
                        _now_iso(),
                    ),
                )
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                # UNIQUE约束冲突，说明已存在
                return False

    def insert_assets_batch(self, assets: list[AssetRecord]) -> int:
        """批量插入资产，利用UNIQUE约束保证幂等

        Args:
            assets: 资产记录列表

        Returns:
            实际插入的数量（跳过重复的）
        """
        inserted = 0
        with self._lock:
            for asset in assets:
                try:
                    self._db.execute(
                        """
                        INSERT INTO assets (
                            asset_id, project_id, user_id, name, duration_ms, type,
                            source_path, source_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            asset.asset_id,
                            asset.project_id,
                            asset.user_id,
                            asset.name,
                            asset.duration_ms,
                            asset.type,
                            asset.source_path,
                            asset.source_hash,
                            _now_iso(),
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    # UNIQUE约束冲突，跳过
                    continue
            self._db.commit()
        return inserted

    def get_asset_by_id(self, asset_id: str, project_id: str, user_id: str) -> dict[str, Any] | None:
        """根据ID获取资产

        Args:
            asset_id: 资产ID
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            资产字典，不存在则返回None
        """
        with self._lock:
            cursor = self._db.execute(
                """
                SELECT asset_id, project_id, user_id, name, duration_ms, type,
                       source_path, source_hash
                FROM assets
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
                    "name": row[3],
                    "duration_ms": row[4],
                    "type": row[5],
                    "source_path": row[6],
                    "source_hash": row[7],
                }
            return None

    def list_assets_by_project(self, project_id: str, user_id: str) -> list[dict[str, Any]]:
        """列出项目下所有资产

        Args:
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            资产字典列表
        """
        with self._lock:
            cursor = self._db.execute(
                """
                SELECT asset_id, project_id, user_id, name, duration_ms, type,
                       source_path, source_hash
                FROM assets
                WHERE project_id = ? AND user_id = ?
                ORDER BY created_at DESC
                """,
                (project_id, user_id),
            )
            return [
                {
                    "asset_id": row[0],
                    "project_id": row[1],
                    "user_id": row[2],
                    "name": row[3],
                    "duration_ms": row[4],
                    "type": row[5],
                    "source_path": row[6],
                    "source_hash": row[7],
                }
                for row in cursor.fetchall()
            ]

    def delete_asset(self, asset_id: str, project_id: str, user_id: str) -> bool:
        """删除资产

        Args:
            asset_id: 资产ID
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            True表示删除成功，False表示不存在
        """
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM assets WHERE asset_id = ? AND project_id = ? AND user_id = ?",
                (asset_id, project_id, user_id),
            )
            self._db.commit()
            return cursor.rowcount > 0

    def count_assets_by_project(self, project_id: str, user_id: str) -> int:
        """统计项目下的资产数量

        Args:
            project_id: 项目ID
            user_id: 用户ID

        Returns:
            资产数量
        """
        with self._lock:
            cursor = self._db.execute(
                "SELECT COUNT(*) FROM assets WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            return cursor.fetchone()[0]
