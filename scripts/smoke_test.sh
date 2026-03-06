#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
CORE_PORT="${CORE_PORT:-8000}"
SERVER_PORT="${SERVER_PORT:-8001}"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"
source "${ROOT_DIR}/server/venv/bin/activate"

CORE_LOG="${LOG_DIR}/smoke_core.log"
SERVER_LOG="${LOG_DIR}/smoke_server.log"

if ! redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
  redis-server --port 6379 --save "" --appendonly no --daemonize yes --dir "${LOG_DIR}" --logfile "${LOG_DIR}/smoke_redis.log"
fi

start_service() {
  local service_dir="$1"
  local module="$2"
  local port="$3"
  local log_file="$4"
  (
    cd "${service_dir}"
    source venv/bin/activate
    AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
    REDIS_URL="${REDIS_URL}" \
    uvicorn "${module}" --host 127.0.0.1 --port "${port}" > "${log_file}" 2>&1 &
    echo "$!"
  )
}

CORE_PID="$(start_service "${ROOT_DIR}/core" "server:app" "${CORE_PORT}" "${CORE_LOG}")"
SERVER_PID="$(start_service "${ROOT_DIR}/server" "main:app" "${SERVER_PORT}" "${SERVER_LOG}")"
cleanup() {
  kill "${CORE_PID}" "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 40); do
  if curl -s "http://127.0.0.1:${CORE_PORT}/health" >/dev/null 2>&1 && curl -s "http://127.0.0.1:${SERVER_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

TOKEN="$(
  AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
  "${ROOT_DIR}/scripts/issue_dev_token.sh" "smoke_user_001"
)"

PROJECT_JSON="$(
  curl -s \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"title":"Smoke Project"}' \
    "http://127.0.0.1:${CORE_PORT}/api/v1/projects"
)"

CHAT_JSON="$(
  curl -s \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(PROJECT_JSON="${PROJECT_JSON}" python - <<'PY'
import json
import os
project_id = json.loads(os.environ["PROJECT_JSON"])["project_id"]
payload = {"project_id": project_id, "message": "先来一版", "context": {"has_media": False}}
print(json.dumps(payload))
PY
)" \
    "http://127.0.0.1:${SERVER_PORT}/api/v1/chat"
)"

PROJECT_JSON="${PROJECT_JSON}" CHAT_JSON="${CHAT_JSON}" python - <<'PY'
import json
import os

project = json.loads(os.environ["PROJECT_JSON"])
chat = json.loads(os.environ["CHAT_JSON"])

assert project.get("project_id"), "project_id missing"
assert chat.get("decision_type") == "ASK_USER_CLARIFICATION", "unexpected decision_type"
assert isinstance(chat.get("ops"), list) and len(chat["ops"]) > 0, "ops missing"
print("smoke_ok")
PY

echo "Smoke test passed."
