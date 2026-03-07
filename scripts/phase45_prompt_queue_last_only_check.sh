#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_FILE="$(mktemp /tmp/entrocut_prompt_queue_last_only_XXXXXX.mjs)"

cleanup() {
  rm -f "${BUNDLE_FILE}"
}
trap cleanup EXIT

if [[ ! -d "${ROOT_DIR}/client/node_modules" ]]; then
  if [[ -n "${CI:-}" || "${INSTALL_CLIENT_DEPS:-}" == "1" ]]; then
    (
      cd "${ROOT_DIR}/client"
      npm ci
    )
  else
    echo "client/node_modules 缺失，无法运行 Prompt queue 校验。"
    echo "可先执行: cd client && npm install"
    exit 1
  fi
fi

(
  cd "${ROOT_DIR}/client"
  ./node_modules/.bin/esbuild ../scripts/phase45_prompt_queue_last_only_check.ts \
    --bundle \
    --platform=node \
    --format=esm \
    --outfile="${BUNDLE_FILE}"
)

node "${BUNDLE_FILE}"

echo "Phase 4/5 prompt queue last-only check passed."
