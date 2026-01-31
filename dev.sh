#!/bin/bash
# ===========================================
# Entrocut 开发环境启动脚本
# ===========================================
# 同时启动三个服务：
# - server: 云端后端 (FastAPI)
# - core: 本地算法 Sidecar (FastAPI)
# - client: Electron 前端
# ===========================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查依赖
check_dependencies() {
  log_info "检查依赖..."

  # 检查 Python
  if ! command -v python3 &> /dev/null; then
    log_error "Python 3 未安装"
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
  jobs -p | xargs -r kill
  wait
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

  # 切换到项目根目录
  cd "$PROJECT_ROOT"

  # 启动 Server (云端后端)
  log_info "启动 Server (端口 8001)..."
  cd "$PROJECT_ROOT/server"
  source venv/bin/activate
  python main.py &
  SERVER_PID=$!
  cd "$PROJECT_ROOT"

  # 等待 Server 启动
  sleep 2

  # 启动 Core (本地算法 Sidecar)
  log_info "启动 Core (端口 8000)..."
  cd "$PROJECT_ROOT/core"
  source venv/bin/activate
  python server.py &
  CORE_PID=$!
  cd "$PROJECT_ROOT"

  # 等待 Core 启动
  sleep 2

  # 启动 Client (Electron)
  log_info "启动 Client (Electron)..."
  cd "$PROJECT_ROOT/client"
  npm run electron:dev

  log_success "所有服务已停止"
}

main "$@"
