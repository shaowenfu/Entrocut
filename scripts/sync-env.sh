#!/bin/bash
#
# 从 GitHub Secrets 同步环境变量到本地 .env
#
# 使用方法：
#   1. 安装 GitHub CLI: https://cli.github.com/
#   2. 登录: gh auth login
#   3. 运行: ./scripts/sync-env.sh
#

set -e

# 配置
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/server/.env"
REPO_NAME="sherwen/Entrocut"  # 修改为你的仓库

echo "=========================================="
echo "Syncing GitHub Secrets to local .env"
echo "=========================================="

# 检查 GitHub CLI
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) not installed"
    echo "Install from: https://cli.github.com/"
    exit 1
fi

# 检查登录状态
if ! gh auth status &> /dev/null; then
    echo "Error: Not logged in to GitHub"
    echo "Run: gh auth login"
    exit 1
fi

# 获取仓库信息
echo "Fetching secrets from $REPO_NAME..."

# 定义需要同步的 Secret 映射 (Secret Name -> Env Variable Name)
declare -A SECRETS_MAP=(
    [DASHSCOPE_API_KEY]="DASHSCOPE_API_KEY"
    [DASHVECTOR_API_KEY]="DASHVECTOR_API_KEY"
    [DASHVECTOR_ENDPOINT]="DASHVECTOR_ENDPOINT"
    [MONGODB_ATLAS_URI]="MONGODB_URI"
)

# 创建 .env 文件头
cat > "$ENV_FILE" << 'EOF'
# ============================================
# Entrocut Server 本地开发环境配置
# 自动从 GitHub Secrets 同步生成
# 最后更新: $(date)
# ============================================

SERVER_PORT=8001
LOG_LEVEL=INFO
CONTRACT_VERSION=0.1.0-mock

EOF

# 读取每个 Secret 并写入 .env
for secret_name in "${!SECRETS_MAP[@]}"; do
    env_name="${SECRETS_MAP[$secret_name]}"

    echo "Fetching $secret_name..."

    # 使用 GitHub CLI 获取 Secret（只用于写入环境变量，不显示内容）
    secret_value=$(gh secret view "$secret_name" --repo "$REPO_NAME" 2>/dev/null || echo "")

    if [ -z "$secret_value" ]; then
        echo "  Warning: $secret_name is empty or not found"
        echo "$env_name=" >> "$ENV_FILE"
    else
        echo "  $env_name = [hidden]"
        echo "$env_name=$secret_value" >> "$ENV_FILE"
    fi
done

echo ""
echo "=========================================="
echo "Sync completed!"
echo "Environment file: $ENV_FILE"
echo ""
echo "⚠️  Warning: This file contains sensitive information."
echo "   Make sure it's in .gitignore and never committed."
echo "=========================================="
