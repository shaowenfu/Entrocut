#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
CORE_PORT="${CORE_PORT:-8010}"
SERVER_PORT="${SERVER_PORT:-8011}"
CLIENT_PORT="${CLIENT_PORT:-5174}"
CORE_DB_PATH="${CORE_DB_PATH:-/tmp/entrocut_phase45_core.db}"
SERVER_DB_PATH="${SERVER_DB_PATH:-/tmp/entrocut_phase45_server.db}"
SERVER_BASE_URL="http://127.0.0.1:${SERVER_PORT}"
LOG_DIR="${ROOT_DIR}/logs"

mkdir -p "${LOG_DIR}"
rm -f "${CORE_DB_PATH}" "${SERVER_DB_PATH}"

CORE_LOG="${LOG_DIR}/phase45_core.log"
SERVER_LOG="${LOG_DIR}/phase45_server.log"
CLIENT_LOG="${LOG_DIR}/phase45_client.log"
REDIS_LOG="${LOG_DIR}/phase45_redis.log"

if ! redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
  redis-server --port 6379 --save "" --appendonly no --daemonize yes --dir "${LOG_DIR}" --logfile "${REDIS_LOG}"
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
    CORE_DB_PATH="${CORE_DB_PATH}" \
    SERVER_DB_PATH="${SERVER_DB_PATH}" \
    SERVER_BASE_URL="${SERVER_BASE_URL}" \
    nohup uvicorn "${module}" --host 127.0.0.1 --port "${port}" > "${log_file}" 2>&1 &
    echo "$!"
  )
}

CORE_PID="$(start_service "${ROOT_DIR}/core" "server:app" "${CORE_PORT}" "${CORE_LOG}")"
SERVER_PID="$(start_service "${ROOT_DIR}/server" "main:app" "${SERVER_PORT}" "${SERVER_LOG}")"

cleanup() {
  kill "${CORE_PID}" "${SERVER_PID}" "${CLIENT_PID:-}" "${WS_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if \
    curl -sS "http://127.0.0.1:${CORE_PORT}/health" >/dev/null 2>&1 && \
    curl -sS "http://127.0.0.1:${SERVER_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

TOKEN="$(
  AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
  "${ROOT_DIR}/scripts/issue_dev_token.sh" "phase45_user_001"
)"

(
  cd "${ROOT_DIR}/client"
  if [[ ! -d node_modules ]]; then
    echo "client/node_modules 缺失，无法运行三端冒烟测试。"
    exit 1
  fi
  VITE_AUTH_TOKEN="${TOKEN}" \
  nohup npm run dev -- --host 127.0.0.1 --port "${CLIENT_PORT}" > "${CLIENT_LOG}" 2>&1 &
  CLIENT_PID="$!"
  echo "${CLIENT_PID}" > /tmp/entrocut_phase45_client.pid
)
CLIENT_PID="$(cat /tmp/entrocut_phase45_client.pid)"

for _ in $(seq 1 60); do
  if curl -sS "http://127.0.0.1:${CLIENT_PORT}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

TMP_VIDEO="$(mktemp /tmp/entrocut_phase45_video_XXXXXX.mp4)"
printf 'mock-video' > "${TMP_VIDEO}"

PROJECT_JSON="$(
  curl -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "files=@${TMP_VIDEO};type=video/mp4" \
    "http://127.0.0.1:${CORE_PORT}/api/v1/projects/upload"
)"

PROJECT_ID="$(
  (
    cd "${ROOT_DIR}/server"
    source venv/bin/activate
    PROJECT_JSON="${PROJECT_JSON}" python - <<'PY'
import json
import os
print(json.loads(os.environ["PROJECT_JSON"])["project_id"])
PY
  )
)"

WS_EVENTS_FILE="$(mktemp /tmp/entrocut_phase45_ws_events_XXXXXX.json)"
WS_READY_FILE="$(mktemp /tmp/entrocut_phase45_ws_ready_XXXXXX.txt)"
rm -f "${WS_READY_FILE}"

(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  WS_URL="ws://127.0.0.1:${CORE_PORT}/ws/projects/${PROJECT_ID}" \
  WS_EVENTS_FILE="${WS_EVENTS_FILE}" \
  WS_READY_FILE="${WS_READY_FILE}" \
  python - <<'PY'
import asyncio
import json
import os

import websockets

url = os.environ["WS_URL"]
events_file = os.environ["WS_EVENTS_FILE"]
ready_file = os.environ["WS_READY_FILE"]
required = {
    "session.ready",
    "media.processing.progress",
    "media.processing.completed",
    "workspace.chat.received",
    "workspace.chat.ready",
    "workspace.patch.ready",
}

async def main() -> None:
    seen: list[str] = []
    async with websockets.connect(url) as websocket:
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=20)
            payload = json.loads(raw)
            event = str(payload.get("event"))
            seen.append(event)
            if event == "session.ready":
                with open(ready_file, "w", encoding="utf-8") as handle:
                    handle.write("ready")
            if required.issubset(set(seen)):
                break
    with open(events_file, "w", encoding="utf-8") as handle:
        json.dump(seen, handle)

asyncio.run(main())
PY
) &
WS_PID="$!"

for _ in $(seq 1 20); do
  if [[ -f "${WS_READY_FILE}" ]]; then
    break
  fi
  sleep 0.2
done

if [[ ! -f "${WS_READY_FILE}" ]]; then
  echo "WebSocket did not become ready."
  exit 1
fi

INGEST_JSON="$(
  curl -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"${PROJECT_ID}\"}" \
    "http://127.0.0.1:${CORE_PORT}/api/v1/ingest"
)"

INDEX_PAYLOAD="$(
  (
    cd "${ROOT_DIR}/server"
    source venv/bin/activate
    INGEST_JSON="${INGEST_JSON}" python - <<'PY'
import json
import os

ingest = json.loads(os.environ["INGEST_JSON"])
print(json.dumps({"project_id": ingest["project_id"], "clips": ingest["clips"]}))
PY
  )
)"

INDEX_JSON="$(
  curl -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${INDEX_PAYLOAD}" \
    "http://127.0.0.1:${CORE_PORT}/api/v1/index/upsert-clips"
)"

CHAT_PAYLOAD="$(
  (
    cd "${ROOT_DIR}/server"
    source venv/bin/activate
    INGEST_JSON="${INGEST_JSON}" python - <<'PY'
import json
import os

ingest = json.loads(os.environ["INGEST_JSON"])
payload = {
    "project_id": ingest["project_id"],
    "message": "做一版高燃滑雪集锦",
    "context": {
        "has_media": True,
        "clip_count": len(ingest["clips"]),
        "asset_count": len(ingest["assets"]),
    },
}
print(json.dumps(payload))
PY
  )
)"

CHAT_JSON="$(
  curl -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${CHAT_PAYLOAD}" \
    "http://127.0.0.1:${CORE_PORT}/api/v1/chat"
)"

for _ in $(seq 1 60); do
  if ! kill -0 "${WS_PID}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if kill -0 "${WS_PID}" >/dev/null 2>&1; then
  echo "WebSocket listener timed out."
  exit 1
fi

(
  export PROJECT_JSON="${PROJECT_JSON}"
  export INGEST_JSON="${INGEST_JSON}"
  export INDEX_JSON="${INDEX_JSON}"
  export CHAT_JSON="${CHAT_JSON}"
  export WS_EVENTS_FILE="${WS_EVENTS_FILE}"
  export CLIENT_PORT="${CLIENT_PORT}"
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  python - <<'PY'
import json
import os
import urllib.request

project = json.loads(os.environ["PROJECT_JSON"])
ingest = json.loads(os.environ["INGEST_JSON"])
index = json.loads(os.environ["INDEX_JSON"])
chat = json.loads(os.environ["CHAT_JSON"])
with open(os.environ["WS_EVENTS_FILE"], "r", encoding="utf-8") as handle:
    events = json.load(handle)
client_html = urllib.request.urlopen(f"http://127.0.0.1:{os.environ['CLIENT_PORT']}", timeout=5).read().decode("utf-8")

assert project.get("project_id"), "project_id missing"
assert len(ingest.get("assets", [])) > 0, "ingest assets missing"
assert len(ingest.get("clips", [])) > 0, "ingest clips missing"
assert int(index.get("indexed", 0)) > 0, "index result missing"
assert chat.get("decision_type") == "UPDATE_PROJECT_CONTRACT", "chat decision mismatch"
assert "Entrocut" in client_html, "client root did not load expected app shell"
required = {
    "session.ready",
    "media.processing.progress",
    "media.processing.completed",
    "workspace.chat.received",
    "workspace.chat.ready",
    "workspace.patch.ready",
}
assert required.issubset(set(events)), f"missing ws events: {required - set(events)}"
print("phase45_smoke_ok")
PY
)

echo "Phase 4/5 smoke test passed."
