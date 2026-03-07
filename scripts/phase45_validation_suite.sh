#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

bash "${ROOT_DIR}/scripts/test_unit.sh"
SERVER_PORT="${SERVER_PORT:-8031}" \
SERVER_DB_PATH="${SERVER_DB_PATH:-/tmp/entrocut_phase45_suite_plan.db}" \
bash "${ROOT_DIR}/scripts/phase45_server_plan_stability.sh"
CORE_PORT="${CORE_PORT:-8032}" \
SERVER_PORT="${SERVER_PORT:-8033}" \
CORE_DB_PATH="${CORE_DB_PATH:-/tmp/entrocut_phase45_suite_recovery_core.db}" \
SERVER_DB_PATH="${SERVER_DB_PATH:-/tmp/entrocut_phase45_suite_recovery_server.db}" \
bash "${ROOT_DIR}/scripts/phase45_disconnect_recovery_test.sh"
CORE_PORT="${CORE_PORT:-8020}" \
SERVER_PORT="${SERVER_PORT:-8021}" \
CLIENT_PORT="${CLIENT_PORT:-5175}" \
CORE_DB_PATH="${CORE_DB_PATH:-/tmp/entrocut_phase45_suite_core.db}" \
SERVER_DB_PATH="${SERVER_DB_PATH:-/tmp/entrocut_phase45_suite_server.db}" \
bash "${ROOT_DIR}/scripts/phase45_smoke_test.sh"

echo "Phase 4/5 validation suite passed."
