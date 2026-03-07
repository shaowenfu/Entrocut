#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
CORE_PORT="${CORE_PORT:-8010}"
SERVER_PORT="${SERVER_PORT:-8011}"
CORE_DB_PATH="${CORE_DB_PATH:-/tmp/entrocut_phase45_recovery_core.db}"
SERVER_DB_PATH="${SERVER_DB_PATH:-/tmp/entrocut_phase45_recovery_server.db}"
SERVER_BASE_URL="http://127.0.0.1:${SERVER_PORT}"
LOG_DIR="${ROOT_DIR}/logs"
CORE_LOG="${LOG_DIR}/phase45_recovery_core.log"
SERVER_LOG="${LOG_DIR}/phase45_recovery_server.log"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

mkdir -p "${LOG_DIR}"
rm -f "${CORE_DB_PATH}" "${SERVER_DB_PATH}"

if ! redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
  redis-server --port 6379 --save "" --appendonly no --daemonize yes --dir "${LOG_DIR}" --logfile "${LOG_DIR}/phase45_recovery_redis.log"
fi

start_core() {
  (
    cd "${ROOT_DIR}/core"
    source venv/bin/activate
    AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
    REDIS_URL="${REDIS_URL}" \
    CORE_DB_PATH="${CORE_DB_PATH}" \
    SERVER_BASE_URL="${SERVER_BASE_URL}" \
    nohup uvicorn server:app --host 127.0.0.1 --port "${CORE_PORT}" < /dev/null > "${CORE_LOG}" 2>&1 &
    echo "$!"
  )
}

start_server() {
  (
    cd "${ROOT_DIR}/server"
    source venv/bin/activate
    AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
    REDIS_URL="${REDIS_URL}" \
    SERVER_DB_PATH="${SERVER_DB_PATH}" \
    nohup uvicorn main:app --host 127.0.0.1 --port "${SERVER_PORT}" < /dev/null > "${SERVER_LOG}" 2>&1 &
    echo "$!"
  )
}

wait_for_http_up() {
  local url="$1"
  for _ in $(seq 1 60); do
    if curl --noproxy '*' -sS -m 1 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

wait_for_http_down() {
  local url="$1"
  for _ in $(seq 1 60); do
    if ! curl --noproxy '*' -sS -m 1 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

CORE_PID="$(start_core)"
SERVER_PID="$(start_server)"

cleanup() {
  kill "${CORE_PID:-}" "${SERVER_PID:-}" "${WS_MONITOR_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT

wait_for_http_up "http://127.0.0.1:${CORE_PORT}/health" || {
  echo "Core health check did not become ready."
  exit 1
}
wait_for_http_up "http://127.0.0.1:${SERVER_PORT}/health" || {
  echo "Server health check did not become ready."
  exit 1
}

TOKEN="$(
  AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
  "${ROOT_DIR}/scripts/issue_dev_token.sh" "phase45_recovery_user_001"
)"

PROJECT_JSON="$(
  curl --noproxy '*' -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"title":"Recovery Project"}' \
    "http://127.0.0.1:${CORE_PORT}/api/v1/projects"
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

(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  WS_URL="ws://127.0.0.1:${CORE_PORT}/ws/projects/${PROJECT_ID}?access_token=${TOKEN}&session_id=phase45_recovery_session&last_sequence=0" python - <<'PY'
import asyncio
import json
import os

import websockets


async def wait_for_session_ready(websocket) -> None:
    for _ in range(5):
        payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if payload.get("event") == "session.ready":
            return
    raise AssertionError("initial ws session.ready missing")


async def main() -> None:
    async with websockets.connect(os.environ["WS_URL"]) as websocket:
        await wait_for_session_ready(websocket)


asyncio.run(main())
print("ws_initial_connect_ok")
PY
)

(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  WS_URL="ws://127.0.0.1:${CORE_PORT}/ws/projects/${PROJECT_ID}?access_token=${TOKEN}&session_id=phase45_recovery_session&last_sequence=0" python - <<'PY'
import asyncio
import json
import os

import websockets


async def wait_for_session_ready(websocket) -> None:
    for _ in range(5):
        payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if payload.get("event") == "session.ready":
            return
    raise AssertionError("reconnect ws session.ready missing")


async def main() -> None:
    async with websockets.connect(os.environ["WS_URL"]) as websocket:
        await wait_for_session_ready(websocket)


asyncio.run(main())
print("ws_reconnect_ok")
PY
)

kill "${SERVER_PID}"
wait_for_http_down "http://127.0.0.1:${SERVER_PORT}/health" || {
  echo "Server did not stop cleanly."
  exit 1
}

FAILED_CHAT_BODY="$(mktemp /tmp/entrocut_recovery_failed_chat_XXXXXX.json)"
FAILED_CHAT_STATUS="$(
  curl --noproxy '*' -sS \
    -o "${FAILED_CHAT_BODY}" \
    -w '%{http_code}' \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"${PROJECT_ID}\",\"message\":\"retry after failure\",\"context\":{\"has_media\":false}}" \
    "http://127.0.0.1:${CORE_PORT}/api/v1/chat" || true
)"

(
  export FAILED_CHAT_STATUS="${FAILED_CHAT_STATUS}"
  export FAILED_CHAT_BODY="${FAILED_CHAT_BODY}"
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  python - <<'PY'
import json
import os

status = os.environ["FAILED_CHAT_STATUS"]
with open(os.environ["FAILED_CHAT_BODY"], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

assert status == "502", f"expected 502 when server is down, got {status}"
error = payload.get("error") or {}
assert error.get("code") in {"SERVER_UNAVAILABLE", "SERVER_PROXY_HTTP_ERROR"}, "unexpected core proxy failure code"
print("server_down_failure_ok")
PY
)
rm -f "${FAILED_CHAT_BODY}"

SERVER_PID="$(start_server)"
wait_for_http_up "http://127.0.0.1:${SERVER_PORT}/health" || {
  echo "Server did not recover."
  exit 1
}

RECOVERED_CHAT_JSON="$(
  curl --noproxy '*' -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"${PROJECT_ID}\",\"message\":\"retry after recovery\",\"context\":{\"has_media\":false}}" \
    "http://127.0.0.1:${CORE_PORT}/api/v1/chat"
)"

(
  export RECOVERED_CHAT_JSON="${RECOVERED_CHAT_JSON}"
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  python - <<'PY'
import json
import os

payload = json.loads(os.environ["RECOVERED_CHAT_JSON"])
assert payload.get("decision_type") == "ASK_USER_CLARIFICATION", "server recovery chat decision mismatch"
print("server_recovery_ok")
PY
)

WS_READY_FILE="$(mktemp /tmp/entrocut_recovery_ws_ready_XXXXXX.txt)"
WS_CLOSED_FILE="$(mktemp /tmp/entrocut_recovery_ws_closed_XXXXXX.txt)"
(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  WS_URL="ws://127.0.0.1:${CORE_PORT}/ws/projects/${PROJECT_ID}?access_token=${TOKEN}&session_id=phase45_recovery_session&last_sequence=0" \
  WS_READY_FILE="${WS_READY_FILE}" \
  WS_CLOSED_FILE="${WS_CLOSED_FILE}" \
  python - <<'PY'
import asyncio
import json
import os

import websockets
from websockets.exceptions import ConnectionClosed


async def wait_for_session_ready(websocket) -> None:
    for _ in range(5):
        payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if payload.get("event") == "session.ready":
            return
    raise AssertionError("ws monitor missing session.ready")


async def main() -> None:
    try:
        async with websockets.connect(os.environ["WS_URL"]) as websocket:
            await wait_for_session_ready(websocket)
            with open(os.environ["WS_READY_FILE"], "w", encoding="utf-8") as handle:
                handle.write("ready")
            while True:
                await websocket.recv()
    except ConnectionClosed:
        pass
    except Exception:
        if not os.path.exists(os.environ["WS_READY_FILE"]):
            raise
    with open(os.environ["WS_CLOSED_FILE"], "w", encoding="utf-8") as handle:
        handle.write("closed")


asyncio.run(main())
PY
) &
WS_MONITOR_PID="$!"

for _ in $(seq 1 50); do
  if [[ -f "${WS_READY_FILE}" ]]; then
    break
  fi
  sleep 0.2
done

if [[ ! -f "${WS_READY_FILE}" ]]; then
  echo "WebSocket monitor did not become ready."
  exit 1
fi

kill "${CORE_PID}"
wait_for_http_down "http://127.0.0.1:${CORE_PORT}/health" || {
  echo "Core did not stop cleanly."
  exit 1
}

for _ in $(seq 1 50); do
  if [[ -f "${WS_CLOSED_FILE}" ]]; then
    break
  fi
  sleep 0.2
done

if [[ ! -f "${WS_CLOSED_FILE}" ]]; then
  echo "WebSocket monitor did not observe core disconnect."
  exit 1
fi

wait "${WS_MONITOR_PID}" || true

CORE_PID="$(start_core)"
wait_for_http_up "http://127.0.0.1:${CORE_PORT}/health" || {
  echo "Core did not recover."
  exit 1
}

(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  WS_URL="ws://127.0.0.1:${CORE_PORT}/ws/projects/${PROJECT_ID}?access_token=${TOKEN}&session_id=phase45_recovery_session&last_sequence=0" python - <<'PY'
import asyncio
import json
import os

import websockets


async def wait_for_session_ready(websocket) -> None:
    for _ in range(5):
        payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if payload.get("event") == "session.ready":
            return
    raise AssertionError("ws reconnect after core restart missing")


async def main() -> None:
    async with websockets.connect(os.environ["WS_URL"]) as websocket:
        await wait_for_session_ready(websocket)


asyncio.run(main())
print("core_recovery_ws_ok")
PY
)

rm -f "${WS_READY_FILE}" "${WS_CLOSED_FILE}"

echo "Phase 4/5 disconnect recovery test passed."
