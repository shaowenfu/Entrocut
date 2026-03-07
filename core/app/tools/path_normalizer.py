"""路径规范化工具 - 处理跨平台路径规范化、软链接解析和稳定hash生成"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.tools.registry import ToolResult


class PathNormalizerTool:
    """路径规范化工具

    职责：
    1. 解析软链接，获取真实路径
    2. 规范化Windows驱动器大小写
    3. 生成稳定的source_hash用于去重
    """

    name = "path_normalizer"

    def run(
        self,
        raw_path: str,
        *,
        follow_symlinks: bool = True,
        normalize_case: bool = True,
    ) -> ToolResult:
        """规范化路径并生成稳定hash

        Args:
            raw_path: 原始路径
            follow_symlinks: 是否解析软链接（默认True）
            normalize_case: 是否规范化大小写（Windows下默认True）

        Returns:
            ToolResult with payload:
                - normalized_path: str - 规范化后的绝对路径
                - canonical_path: str - 解析软链接后的真实路径
                - source_hash: str - 稳定的去重hash（32位hex）
                - is_symlink: bool - 是否是软链接
                - original_path: str - 原始路径
        """
        try:
            original = Path(raw_path)

            # 1. 解析软链接
            if follow_symlinks:
                canonical = original.resolve()
            else:
                canonical = original.absolute()

            is_symlink = original.is_symlink()

            # 2. Windows驱动器大小写规范化
            normalized = str(canonical)
            if normalize_case and os.name == "nt":
                # Windows: 保持驱动器小写，其余保持原样
                if len(normalized) >= 2 and normalized[1] == ":":
                    normalized = normalized[0].lower() + normalized[1:]

            # 3. 生成稳定hash（使用规范化的绝对路径）
            # 关键：用canonical_path的字符串形式，保证软链接和原文件hash一致
            hash_input = normalized if normalize_case else str(canonical)
            source_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:32]

            return ToolResult(
                ok=True,
                payload={
                    "normalized_path": normalized,
                    "canonical_path": str(canonical),
                    "source_hash": source_hash,
                    "is_symlink": is_symlink,
                    "original_path": raw_path,
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                payload={
                    "error": str(e),
                    "original_path": raw_path,
                },
            )
