"""媒体扫描工具 - 扫描目录并支持幂等去重"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.path_normalizer import PathNormalizerTool
from app.tools.registry import ToolResult


class MediaScannerTool:
    """媒体扫描工具

    职责：
    1. 扫描目录中的媒体文件
    2. 利用PathNormalizerTool规范化路径
    3. 通过source_hash实现幂等去重
    """

    name = "media_scanner"

    # 支持的视频格式
    DEFAULT_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".flv", ".wmv"}

    def __init__(self, path_normalizer: PathNormalizerTool | None = None):
        self._normalizer = path_normalizer or PathNormalizerTool()

    def run(
        self,
        folder_path: str,
        *,
        existing_hashes: set[str] | None = None,
        extensions: set[str] | None = None,
    ) -> ToolResult:
        """扫描目录，返回新增资产（跳过已存在）

        Args:
            folder_path: 要扫描的目录路径
            existing_hashes: 已存在的source_hash集合（用于去重）
            extensions: 支持的文件扩展名集合（默认为视频格式）

        Returns:
            ToolResult with payload:
                - new_assets: list[dict] - 新增资产列表
                - skipped_count: int - 跳过的重复数量
                - total_found: int - 发现的总文件数
                - scan_errors: list[str] - 扫描错误列表
                - filtered_count: int - 被过滤掉的非媒体文件数
        """
        if existing_hashes is None:
            existing_hashes = set()

        if extensions is None:
            extensions = self.DEFAULT_EXTENSIONS

        folder = Path(folder_path)
        new_assets: list[dict[str, Any]] = []
        skipped = 0
        errors: list[str] = []
        filtered = 0

        # 检查目录是否存在
        if not folder.exists():
            return ToolResult(
                ok=False,
                payload={
                    "error": f"folder_not_found:{folder_path}",
                    "new_assets": [],
                    "skipped_count": 0,
                    "total_found": 0,
                    "scan_errors": [],
                    "filtered_count": 0,
                },
            )

        if not folder.is_dir():
            return ToolResult(
                ok=False,
                payload={
                    "error": f"not_a_directory:{folder_path}",
                    "new_assets": [],
                    "skipped_count": 0,
                    "total_found": 0,
                    "scan_errors": [],
                    "filtered_count": 0,
                },
            )

        # 递归扫描所有文件
        try:
            for child in sorted(folder.rglob("*")):
                if not child.is_file():
                    continue

                # 过滤非媒体文件
                if child.suffix.lower() not in extensions:
                    filtered += 1
                    continue

                # 规范化路径
                norm_result = self._normalizer.run(str(child))
                if not norm_result.ok:
                    errors.append(f"normalize_failed:{child}: {norm_result.payload.get('error', 'unknown')}")
                    continue

                source_hash = norm_result.payload["source_hash"]

                # 幂等检查：跳过已存在
                if source_hash in existing_hashes:
                    skipped += 1
                    continue

                new_assets.append(
                    {
                        "path": str(child),
                        "name": child.name,
                        "normalized_path": norm_result.payload["normalized_path"],
                        "source_hash": source_hash,
                        "is_symlink": norm_result.payload["is_symlink"],
                    }
                )
        except Exception as e:
            return ToolResult(
                ok=False,
                payload={
                    "error": f"scan_error:{str(e)}",
                    "new_assets": new_assets,
                    "skipped_count": skipped,
                    "total_found": len(new_assets) + skipped,
                    "scan_errors": errors,
                    "filtered_count": filtered,
                },
            )

        return ToolResult(
            ok=True,
            payload={
                "new_assets": new_assets,
                "skipped_count": skipped,
                "total_found": len(new_assets) + skipped,
                "scan_errors": errors,
                "filtered_count": filtered,
            },
        )
