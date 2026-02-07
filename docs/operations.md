## 1. 代码仓库策略 (Repository Strategy)

建议采用 **单代码仓库 (Monorepo)** 模式。

- **理由**：客户端、算法内核、后端 API 之间存在高度的协议耦合（如 JSON Schema）。放在一个仓库可以确保版本同步，避免“接口改了但客户端没跟上”的问题。

### 仓库目录结构复习

```
/root
  ├── .github/workflows/ (GitHub Actions 配置文件)
  ├── client/            (Electron + React)
  ├── core/              (Python Algorithm Sidecar)
  ├── server/            (FastAPI Backend)
  └── docker-compose.yml (用于后端容器化部署)

```

## 2. Git 协作流程 (Git Flow)

团队应遵循以下分支管理规则：

1. **main 分支**：生产环境代码，仅允许通过 Pull Request (PR) 合并，且必须通过自动化测试。
2. **deve 分支**：开发主分支，所有功能分支在此汇总。
3. **feature/xxx 分支**：个人开发分支，完成后提交 PR 指向 develop。
4. **agent/xxx 分支**：各个编程agent分支。
4. **Code Review**：合并 PR 前，必须至少有一名其他成员审核代码。

## 3. GitHub Actions 自动化流水线 (CI/CD)

我们将配置以下流水线（Workflows）：

### A. 客户端构建 (Client CD)

- **触发条件**：当 `main` 分支有新的 `tag` (如 `v1.0.0`) 时。
- **任务**：
    1. 安装 Node.js 和 Python 环境。
    2. 在 Windows/macOS 虚拟运行环境下打包 Electron。
    3. 利用 `electron-builder` 生成 `.exe` 或 `.dmg` 安装包。
    4. **产物**：自动上传至 GitHub Releases 供用户下载。

### B. 后端部署 (Server CD - GHCR + 阿里云 ECS)

- **触发条件**：推送代码至 `main` 分支，或手动触发。
- **任务流**：
    1. **Build**: 在 GitHub Actions Runner 上构建服务端 Docker 镜像。
    2. **Push**: 将镜像推送到 **GitHub Container Registry (GHCR)**。
    3. **Deploy**: 通过 SSH 登录阿里云 ECS，执行 `docker pull` 并重启服务。
    4. **Cleanup**: 清理 GitHub 端和 ECS 端的旧镜像（各保留最新 2 个）。

#### 部署架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions (Runner)                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. 构建镜像 (docker/build-push-action@v5)              │   │
│  │ 2. 推送到 GHCR (ghcr.io/{owner}/{repo}:tag)            │   │
│  │ 3. SSH 登录阿里云 ECS                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      阿里云 ECS                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 4. docker login ghcr.io                                 │   │
│  │ 5. docker pull 新镜像                                    │   │
│  │ 6. 停止/删除旧容器                                       │   │
│  │ 7. 启动新容器 (--restart unless-stopped)                │   │
│  │ 8. 健康检查 (curl /health)                              │   │
│  │ 9. 清理旧镜像（保留最新 2 个）                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 镜像命名

- **Latest**: `ghcr.io/{owner}/{repo}:latest`
- **Commit**: `ghcr.io/{owner}/{repo}:commit-{sha}`
- 示例：`ghcr.io/sherwen/Entrocut:latest`

## 4. 部署至阿里云的详细步骤

### 准备工作

1. **阿里云端**：
    - 准备一台 **ECS 服务器**，安装 Docker。
    - 确保 ECS 安全组开放 8001 端口（Server 服务端口）和 22 端口（SSH）。

2. **GitHub 端**：
    - 在仓库设置中进入 `Settings > Secrets and variables > Actions`，添加以下 **Secrets**：
        - `SERVER_SSH_HOST`: 阿里云 ECS 的公网 IP。
        - `SERVER_SSH_USER`: SSH 登录用户名（如 `root` 或 `ubuntu`）。
        - `SERVER_SSH_KEY`: SSH 私钥（用于无密码登录 ECS）。
        - `SERVER_SSH_PORT`: SSH 端口（可选，默认 22）。

3. **权限配置**：
    - 工作流文件中已配置 `packages: write` 权限，用于推送和删除 GHCR 镜像。

### SSH 密钥配置（ECS 端）

在 ECS 服务器上生成密钥对：

```bash
# 生成密钥对
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions

# 将公钥添加到 authorized_keys
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys

# 复制私钥内容，添加到 GitHub Secrets
cat ~/.ssh/github_actions
```

将私钥内容完整复制到 GitHub Repository Secret `SERVER_SSH_KEY` 中。

### 自动部署工作流

配置文件位于 `.github/workflows/deploy.yml`，包含以下步骤：

1. **Checkout 代码**: 使用 `actions/checkout@v4`
2. **设置 Docker Buildx**: 使用 `docker/setup-buildx-action@v3`
3. **登录 GHCR**: 使用 `docker/login-action@v3`（自动使用 `GITHUB_TOKEN`）
4. **构建并推送**: 使用 `docker/build-push-action@v5`
5. **SSH 部署到 ECS**: 使用 `appleboy/ssh-action@v1.0.0`
6. **清理旧镜像**: 使用 `actions/delete-package-versions@v5`（GitHub 端）+ Shell 脚本（ECS 端）

### 手动触发部署

在 GitHub 仓库页面：

1. 进入 **Actions** 标签
2. 选择 **Deploy Server to ECS** 工作流
3. 点击 **Run workflow** 按钮
4. 选择分支并确认执行

### 清理策略

- **GitHub 端**: 使用 `actions/delete-package-versions@v5`，保留最新 2 个版本
- **ECS 端**: Shell 脚本清理，保留最新 2 个镜像

```bash
# ECS 端清理逻辑
docker images ghcr.io/${IMAGE_NAME} \
  --format "{{.ID}} {{.Tag}}" | \
  sort -k2 -r | \
  tail -n +3 | \
  awk '{print $1}' | \
  xargs -r docker rmi -f
```

## 5. 其它协作细节补充

### A. 环境变量管理

#### 环境变量分层策略

| 环境 | 配置存储 | 注入方式 | 维护者 |
|------|----------|----------|--------|
| **本地开发** | `server/.env`（本地不提交） | 直接读取 | 开发者 |
| **ECS 生产** | GitHub Secrets | `docker run -e` | DevOps |

#### GitHub Secrets 配置清单

生产环境所有敏感配置存储在 GitHub Repository Secrets 中：

| Secret 名称 | 说明 | 示例值 |
|-------------|------|--------|
| `SERVER_SSH_HOST` | ECS 公网 IP | `47.100.1.2` |
| `SERVER_SSH_USER` | SSH 用户名 | `root` |
| `SERVER_SSH_KEY` | SSH 私钥 | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | `sk-xxxxxxxx` |
| `DASHVECTOR_API_KEY` | 向量库 API Key | `sk-xxxxxxxx` |
| `DASHVECTOR_ENDPOINT` | 向量库地址 | `https://xxxxxxxx.dashvector.aliyuncs.com` |
| `MONGODB_ATLAS_URI` | MongoDB 连接字符串 | `mongodb+srv://...` |

#### 更新环境变量流程

**重要**：容器启动时环境变量被"冻结"，修改 Secrets 后必须重新部署才能生效。

```
1. GitHub → Settings → Secrets → 修改 Secret
2. GitHub → Actions → Deploy Server to ECS → Run workflow
3. 等待部署完成（1-2 分钟）
4. 新容器使用最新的环境变量
```

#### 本地开发环境配置

本地使用 `.env` 文件（不提交到 Git）：

```bash
# 从模板创建本地配置
cp server/.env.example server/.env
# 手动填写真实的 API Key
```

**同步 GitHub Secrets 到本地（可选）**：

使用提供的脚本 `scripts/sync-env.sh` 从 GitHub Secrets 拉取最新配置到本地 `.env`：

```bash
# 需要先安装 GitHub CLI
# apt install gh  # Ubuntu/Debian
# brew install gh  # macOS

# 登录 GitHub
gh auth login

# 同步 Secrets 到本地
./scripts/sync-env.sh
```

> ⚠️ **安全提醒**：本地 `.env` 文件包含敏感信息，请勿提交到 Git。

#### ECS 环境配置

**Nginx 反向代理**（使用宝塔面板配置）：

```
代理名称: entrocut-api
目标URL: http://127.0.0.1:8001
发送域名: $host
```

**宝塔面板操作**：
1. 添加网站（域名指向 ECS IP）
2. 设置反向代理到 `127.0.0.1:8001`
3. 申请 SSL 证书（Let's Encrypt）
4. 开启强制 HTTPS

**无需配置**：
- ❌ 不需要 ECS 上的 `.env` 文件
- ❌ 不需要 Nginx 配置文件（宝塔管理）
- ❌ 不需要 SSL 证书配置（宝塔一键申请）

### B. Issue 与项目看板: linear

### C. 结构化日志 (Structured Logging)

- 要求算法端 (Python) 和服务端 (FastAPI) 使用统一的日志格式（如 JSON Log），方便通过 GitHub Actions 运行测试或在生产环境排查问题。

### D. 隐私合规检查

- 启用 GitHub 的 **Secret Scanning** 功能。如果有人不小心将 API Key 写入代码并提交，GitHub 会立即发出警告并拦截。