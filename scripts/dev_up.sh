#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "${LOG_DIR}"

CORE_LOG="${LOG_DIR}/core_${TIMESTAMP}.log"
SERVER_LOG="${LOG_DIR}/server_${TIMESTAMP}.log"
CLIENT_LOG="${LOG_DIR}/client_${TIMESTAMP}.log"
PID_FILE="${LOG_DIR}/dev_up_${TIMESTAMP}.pid"

start_python_service() {
  local service_name="$1"
  local service_dir="$2"
  local app_entry="$3"
  local port="$4"
  local log_file="$5"

  if [[ ! -d "${service_dir}/venv" ]]; then
    echo "[${service_name}] 未检测到 venv，请先手动创建。"
    exit 1
  fi

  (
    cd "${service_dir}"
    source venv/bin/activate
    pip install -r requirements.txt
    nohup uvicorn "${app_entry}" --host 127.0.0.1 --port "${port}" --reload < /dev/null > "${log_file}" 2>&1 &
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
    nohup npm run dev -- --host 127.0.0.1 --port 5173 < /dev/null > "${log_file}" 2>&1 &
    echo "$!" >> "${PID_FILE}"
  )
}

echo "启动时间戳: ${TIMESTAMP}"
echo "PID 文件: ${PID_FILE}"

start_python_service "core" "${ROOT_DIR}/core" "server:app" "8000" "${CORE_LOG}"
start_python_service "server" "${ROOT_DIR}/server" "main:app" "8001" "${SERVER_LOG}"
start_client_service "${ROOT_DIR}/client" "${CLIENT_LOG}"

sleep 2

echo
echo "服务已触发启动。日志文件："
echo "- core:   ${CORE_LOG}"
echo "- server: ${SERVER_LOG}"
echo "- client: ${CLIENT_LOG}"
echo
echo "快速检查："
echo "- curl http://127.0.0.1:8000/health"
echo "- curl http://127.0.0.1:8001/health"
echo "- 打开 http://127.0.0.1:5173"
echo
echo "可选生成开发 Token："
echo "- AUTH_JWT_SECRET=\"${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}\" ./scripts/issue_dev_token.sh"
