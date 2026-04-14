#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_ROOT="${1:-${CORE_DIR}/dist}"

cd "${CORE_DIR}"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "[build_desktop_core] pyinstaller 未安装，请先执行: pip install pyinstaller"
  exit 1
fi

rm -rf build "${OUTPUT_ROOT}/core-dist"
pyinstaller --noconfirm --clean --distpath "${OUTPUT_ROOT}" pyinstaller.spec

if [ ! -d "${OUTPUT_ROOT}/entrocut-core" ]; then
  echo "[build_desktop_core] 构建失败：未找到输出目录 ${OUTPUT_ROOT}/entrocut-core"
  exit 1
fi

mv "${OUTPUT_ROOT}/entrocut-core" "${OUTPUT_ROOT}/core-dist"

echo "[build_desktop_core] 构建完成: ${OUTPUT_ROOT}/core-dist"
