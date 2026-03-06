#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "${LOG_DIR}"

AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}"
AUTH_JWT_ALGORITHM="${AUTH_JWT_ALGORITHM:-HS256}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
CORE_DB_PATH="${CORE_DB_PATH:-${ROOT_DIR}/core/core.db}"
SERVER_DB_PATH="${SERVER_DB_PATH:-${ROOT_DIR}/server/server.db}"
CORE_INGEST_QUEUE_KEY="${CORE_INGEST_QUEUE_KEY:-entrocut:core:ingest}"
SERVER_INDEX_QUEUE_KEY="${SERVER_INDEX_QUEUE_KEY:-entrocut:server:index}"
SERVER_CHAT_QUEUE_KEY="${SERVER_CHAT_QUEUE_KEY:-entrocut:server:chat}"

CORE_LOG="${LOG_DIR}/core_${TIMESTAMP}.log"
SERVER_LOG="${LOG_DIR}/server_${TIMESTAMP}.log"
CLIENT_LOG="${LOG_DIR}/client_${TIMESTAMP}.log"
REDIS_LOG="${LOG_DIR}/redis_${TIMESTAMP}.log"
PID_FILE="${LOG_DIR}/dev_up_${TIMESTAMP}.pid"
REDIS_PID_FILE="${LOG_DIR}/redis_${TIMESTAMP}.pid"

ensure_redis() {
  if redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
    echo "[redis] 已运行，跳过启动。"
    return
  fi

  echo "[redis] 正在启动本地 Redis..."
  redis-server \
    --port 6379 \
    --save "" \
    --appendonly no \
    --daemonize yes \
    --dir "${LOG_DIR}" \
    --logfile "${REDIS_LOG}" \
    --pidfile "${REDIS_PID_FILE}"

  for _ in $(seq 1 20); do
    if redis-cli -u "${REDIS_URL}" ping >/dev/null 2>&1; then
      echo "[redis] 启动成功。"
      if [[ -f "${REDIS_PID_FILE}" ]]; then
        cat "${REDIS_PID_FILE}" >> "${PID_FILE}"
      fi
      return
    fi
    sleep 0.2
  done

  echo "[redis] 启动失败，请检查日志：${REDIS_LOG}"
  exit 1
}

start_python_service() {
  local service_name="$1"
  local service_dir="$2"
  local app_entry="$3"
  local port="$4"
  local log_file="$5"

  if [[ ! -d "${service_dir}/venv" ]]; then
    echo "[${service_name}] 未检测到 venv，正在创建..."
    (
      cd "${service_dir}"
      python -m venv venv
    )
  fi

  (
    cd "${service_dir}"
    source venv/bin/activate
    pip install -r requirements.txt
    AUTH_JWT_SECRET="${AUTH_JWT_SECRET}" \
    AUTH_JWT_ALGORITHM="${AUTH_JWT_ALGORITHM}" \
    REDIS_URL="${REDIS_URL}" \
    CORE_DB_PATH="${CORE_DB_PATH}" \
    SERVER_DB_PATH="${SERVER_DB_PATH}" \
    CORE_INGEST_QUEUE_KEY="${CORE_INGEST_QUEUE_KEY}" \
    SERVER_INDEX_QUEUE_KEY="${SERVER_INDEX_QUEUE_KEY}" \
    SERVER_CHAT_QUEUE_KEY="${SERVER_CHAT_QUEUE_KEY}" \
    nohup uvicorn "${app_entry}" --host 127.0.0.1 --port "${port}" --reload > "${log_file}" 2>&1 &
    echo "$!" >> "${PID_FILE}"
  )
}

start_client_service() {
  local service_dir="$1"
  local log_file="$2"

  (
    cd "${service_dir}"
    if [[ ! -d node_modules ]]; then
      npm install
    fi
    nohup npm run dev -- --host 127.0.0.1 --port 5173 > "${log_file}" 2>&1 &
    echo "$!" >> "${PID_FILE}"
  )
}

echo "启动时间戳: ${TIMESTAMP}"
echo "PID 文件: ${PID_FILE}"
echo "Redis URL: ${REDIS_URL}"
echo "Auth Algorithm: ${AUTH_JWT_ALGORITHM}"

ensure_redis
start_python_service "core" "${ROOT_DIR}/core" "server:app" "8000" "${CORE_LOG}"
start_python_service "server" "${ROOT_DIR}/server" "main:app" "8001" "${SERVER_LOG}"
start_client_service "${ROOT_DIR}/client" "${CLIENT_LOG}"

sleep 2

echo
echo "服务已触发启动。日志文件："
echo "- redis:  ${REDIS_LOG}"
echo "- core:   ${CORE_LOG}"
echo "- server: ${SERVER_LOG}"
echo "- client: ${CLIENT_LOG}"
echo
echo "快速检查："
echo "- redis-cli -u ${REDIS_URL} ping"
echo "- curl http://127.0.0.1:8000/health"
echo "- curl http://127.0.0.1:8001/health"
echo "- 打开 http://127.0.0.1:5173"
echo
echo "生成开发 Token："
echo "- AUTH_JWT_SECRET=\"${AUTH_JWT_SECRET}\" ./scripts/issue_dev_token.sh"
