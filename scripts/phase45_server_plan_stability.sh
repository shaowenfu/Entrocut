#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
SERVER_PORT="${SERVER_PORT:-8011}"
SERVER_DB_PATH="${SERVER_DB_PATH:-/tmp/entrocut_phase45_server_plan.db}"
LOG_DIR="${ROOT_DIR}/logs"
SERVER_LOG="${LOG_DIR}/phase45_server_plan_stability.log"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

mkdir -p "${LOG_DIR}"
rm -f "${SERVER_DB_PATH}"

if ! redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
  redis-server --port 6379 --save "" --appendonly no --daemonize yes --dir "${LOG_DIR}" --logfile "${LOG_DIR}/phase45_server_plan_redis.log"
fi

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

wait_for_health() {
  local url="$1"
  for _ in $(seq 1 60); do
    if curl --noproxy '*' -sS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

SERVER_PID="$(start_server)"
cleanup() {
  kill "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

wait_for_health "http://127.0.0.1:${SERVER_PORT}/health" || {
  echo "Server health check did not become ready."
  exit 1
}

(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  python - <<'PY'
from app.adapters.mock_providers import MockLlmAdapter
from app.services.proxy_services import LLMProxyService

payload = LLMProxyService(adapter=MockLlmAdapter()).plan_edit(
    "generate a high-energy cut",
    context={"source": "plan_stability_check"},
).payload

assert isinstance(payload["reasoning_summary"], str) and payload["reasoning_summary"], "service reasoning_summary invalid"
assert isinstance(payload["ops"], list) and payload["ops"], "service ops invalid"
assert isinstance(payload["storyboard_scenes"], list) and payload["storyboard_scenes"], "service storyboard invalid"
print("service_plan_payload_ok")
PY
)

TOKEN="$(
  AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
  "${ROOT_DIR}/scripts/issue_dev_token.sh" "phase45_plan_user_001"
)"

NO_MEDIA_JSON="$(
  curl --noproxy '*' -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"project_id":"plan_prompt_only","message":"first cut please","context":{"has_media":false}}' \
    "http://127.0.0.1:${SERVER_PORT}/api/v1/chat"
)"

WITH_MEDIA_JSON="$(
  curl --noproxy '*' -sS \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"project_id":"plan_media_ready","message":"make it fast and energetic","context":{"has_media":true,"clip_count":3,"asset_count":1}}' \
    "http://127.0.0.1:${SERVER_PORT}/api/v1/chat"
)"

(
  export NO_MEDIA_JSON="${NO_MEDIA_JSON}"
  export WITH_MEDIA_JSON="${WITH_MEDIA_JSON}"
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  python - <<'PY'
import json
import os

no_media = json.loads(os.environ["NO_MEDIA_JSON"])
with_media = json.loads(os.environ["WITH_MEDIA_JSON"])


def assert_agent_ops(payload: dict, *, label: str) -> None:
    ops = payload.get("ops")
    assert isinstance(ops, list) and ops, f"{label}: ops missing"
    assert all(isinstance(item, dict) for item in ops), f"{label}: ops item must be dict"


def assert_storyboard(payload: dict, *, expected_count: int, label: str) -> None:
    scenes = payload.get("storyboard_scenes")
    assert isinstance(scenes, list), f"{label}: storyboard_scenes missing"
    assert len(scenes) == expected_count, f"{label}: unexpected storyboard scene count"
    for index, scene in enumerate(scenes, start=1):
        assert isinstance(scene, dict), f"{label}: scene {index} must be dict"
        for key in ("id", "title", "duration", "intent"):
            value = scene.get(key)
            assert isinstance(value, str) and value.strip(), f"{label}: scene {index} missing {key}"


assert no_media.get("decision_type") == "ASK_USER_CLARIFICATION", "prompt-only decision mismatch"
assert isinstance(no_media.get("reasoning_summary"), str) and no_media["reasoning_summary"], "prompt-only reasoning missing"
assert_agent_ops(no_media, label="prompt-only")
assert_storyboard(no_media, expected_count=0, label="prompt-only")
assert isinstance(no_media.get("project"), dict), "prompt-only project missing"
assert no_media["project"]["reasoning_summary"] == no_media["reasoning_summary"], "prompt-only reasoning drift"

assert with_media.get("decision_type") == "UPDATE_PROJECT_CONTRACT", "media-ready decision mismatch"
assert isinstance(with_media.get("reasoning_summary"), str) and with_media["reasoning_summary"], "media-ready reasoning missing"
assert_agent_ops(with_media, label="media-ready")
assert_storyboard(with_media, expected_count=3, label="media-ready")
assert isinstance(with_media.get("project"), dict), "media-ready project missing"
timeline = with_media["project"].get("timeline")
assert isinstance(timeline, dict) and isinstance(timeline.get("tracks"), list), "media-ready timeline missing"
assert with_media["project"]["reasoning_summary"] == with_media["reasoning_summary"], "media-ready reasoning drift"
assert isinstance(with_media.get("meta"), dict), "media-ready meta missing"
print("phase45_server_plan_stability_ok")
PY
)

echo "Phase 4/5 server plan stability check passed."
