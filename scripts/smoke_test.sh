#!/usr/bin/env bash
set -euo pipefail

CORE_PORT="${CORE_PORT:-8000}"
SERVER_PORT="${SERVER_PORT:-8001}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

CORE_HEALTH="$(curl --noproxy '*' -sS "http://127.0.0.1:${CORE_PORT}/health")"
SERVER_HEALTH="$(curl --noproxy '*' -sS "http://127.0.0.1:${SERVER_PORT}/health")"

printf '%s\n' "${CORE_HEALTH}" | grep '"service":"core"' >/dev/null
printf '%s\n' "${SERVER_HEALTH}" | grep '"service":"server"' >/dev/null

echo "skeleton_smoke_ok"
