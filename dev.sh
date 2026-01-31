#!/bin/bash
# ===========================================
# Entrocut 开发环境启动脚本
# ===========================================
# 同时启动三个服务：
# - server: 云端后端 (FastAPI)
# - core: 本地算法 Sidecar (FastAPI)
# - client: Electron 前端
# ===========================================

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Python 解释器路径（使用虚拟环境）
SERVER_PYTHON="$PROJECT_ROOT/server/venv/bin/python"
CORE_PYTHON="$PROJECT_ROOT/core/venv/bin/python"

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查并清理端口占用
cleanup_ports() {
  local ports=(8000 8001 5173)
  log_info "检查端口占用..."
  for port in "${ports[@]}"; do
    if lsof -i :"$port" &>/dev/null; then
      log_warn "端口 $port 被占用，正在清理..."
      fuser -k "$port/tcp" &>/dev/null || true
      sleep 1
    fi
  done
}

# 检查依赖
check_dependencies() {
  log_info "检查依赖..."
  
  cleanup_ports

  # 检查虚拟环境
  if [ ! -f "$SERVER_PYTHON" ]; then
    log_error "Server 虚拟环境不存在，请先在 server/ 目录运行: python3 -m venv venv"
    exit 1
  fi

  if [ ! -f "$CORE_PYTHON" ]; then
    log_error "Core 虚拟环境不存在，请先在 core/ 目录运行: python3 -m venv venv"
    exit 1
  fi

  # 检查 Node.js
  if ! command -v node &> /dev/null; then
    log_error "Node.js 未安装"
    exit 1
  fi

  log_success "依赖检查通过"
}

# 清理函数
cleanup() {
  log_info "停止所有服务..."
  jobs -p | xargs -r kill 2>/dev/null || true
  wait 2>/dev/null || true
  log_success "所有服务已停止"
}

# 设置退出时清理
trap cleanup EXIT INT TERM

# ===========================================
# 主流程
# ===========================================

main() {
  log_info "================================"
  log_info "启动 Entrocut 开发环境"
  log_info "================================"

  check_dependencies

  cd "$PROJECT_ROOT"

  # 启动 Server (云端后端)
  log_info "启动 Server (端口 8001)..."
  cd "$PROJECT_ROOT/server"
  "$SERVER_PYTHON" main.py &
  SERVER_PID=$!
  cd "$PROJECT_ROOT"

  # 等待 Server 启动
  sleep 2

  # 启动 Client (Electron)
  # 注意：Core (本地算法 Sidecar) 由 Electron 主进程自动管理启动
  log_info "启动 Client (Electron)..."
  cd "$PROJECT_ROOT/client"
  npm run electron:dev

  log_success "所有服务已停止"
}

main "$@"
