## 1. Repository Strategy（仓库策略）

建议采用 **Monorepo（单代码仓库）** 模式。

- **理由**：客户端、算法内核、后端 API（接口）之间存在高度的协议耦合（如 JSON Schema（JSON 结构规范））。放在一个仓库可以确保版本同步，避免“接口改了但客户端没跟上”的问题。

### 仓库目录结构复习

```
/root
  ├── .github/workflows/ (GitHub Actions（持续集成）配置文件)
  ├── client/            (Electron（桌面框架） + React（前端框架）)
  ├── core/              (Python Sidecar（本地算法服务）)
  ├── server/            (FastAPI（Python Web 框架）Backend（后端）)
  └── docker-compose.yml (用于后端容器化部署)

```

## 2. Git Flow（Git 协作流程）

团队应遵循以下分支管理规则：

1. **`main` Branch（发布分支）**：生产环境代码，仅允许通过 Pull Request（合并请求）合并，且必须通过自动化测试。
2. **`dev` Branch（集成分支）**：统一集成入口，所有 Agent Branch（代理分支）合并至此。
3. **Agent Branch（代理分支）**：固定为 `client-agent`、`server-agent`、`core-agent`、`data-agent`。
4. **Code Review（代码评审）**：合并 PR（合并请求）前，必须至少有一名其他成员审核代码。

协作流程以 `docs/*_agent.md` 为准，Round（轮次）发布与对齐信息见 `docs/coordination/STATUS.md` 与 `docs/coordination/rounds/`。

## 3. GitHub Actions（持续集成）流水线（CI/CD（持续集成/持续部署））

我们将配置两个主要的流水线（Workflows（工作流））：

### A. Client CD（客户端持续部署）

- **触发条件**：当 `main` 分支有新的 `tag`（标签）（如 `v1.0.0`）时。
- **任务**：
    1. 安装 Node.js（运行时）和 Python（解释语言）环境。
    2. 在 Windows/macOS（操作系统）虚拟运行环境下打包 Electron（桌面框架）。
    3. 利用 `electron-builder`（打包工具）生成 `.exe` 或 `.dmg` 安装包。
    4. **产物**：自动上传至 GitHub Releases（发布页）供用户下载。

### B. Server CD（服务端持续部署）- 阿里云

- **触发条件**：推送代码至 `main` 分支。
- **任务流**：
    1. **Build（构建）**: 构建服务端 Docker（容器引擎）镜像。
    2. **Push（推送）**: 将镜像推送到 **阿里云容器镜像服务 ACR（镜像仓库）**。
    3. **Deploy（部署）**: 远程登录阿里云服务器 ECS（云服务器），执行 `docker-compose`（容器编排）`pull` 并重启服务。

## 4. 部署至阿里云的详细步骤

### 准备工作

1. **阿里云端**：
    - 开通 **ACR（容器镜像服务）**，创建命名空间和仓库。
    - 准备一台 **ECS（云服务器）**，安装 Docker（容器引擎）和 Docker Compose（容器编排）。
2. **GitHub 端**：
    - 在仓库设置中进入 `Settings > Secrets and variables > Actions`，添加以下 **Secrets（密钥）**（保护敏感信息）：
        - `ALB_ACR_REGISTRY`: 阿里云镜像地址。
        - `ALB_ACR_USERNAME`: 镜像仓库登录名。
        - `ALB_ACR_PASSWORD`: 镜像仓库登录密码。
        - `SERVER_SSH_HOST`: ECS 服务器公网 IP。
        - `SERVER_SSH_KEY`: 用于登录服务器的私钥。

### 自动部署示例逻辑（YAML（配置格式））

```
# 逻辑简述：
# 1. 登录阿里云 Docker（容器引擎）仓库
# 2. 构建并推送 server（服务端）镜像
# 3. 通过 SSH（远程登录）登录 ECS（云服务器）更新容器

```

## 5. 其它协作细节补充

### A. 环境变量管理 (.env)

- **禁止将 `.env` 文件提交到 GitHub**（在 `.gitignore` 中忽略）。
- 团队内共享一份 `.env.template` 模板文件，列出所有需要的 Key（如 `DASHSCOPE_API_KEY`），但值留空，由成员自行在本地填充。

### B. Issue（问题）与项目看板: Linear（项目看板工具）

### C. Structured Logging（结构化日志）

- 要求算法端（Python（解释语言））和服务端（FastAPI（Python Web 框架））使用统一的日志格式（如 JSON Log（JSON 日志）），方便通过 GitHub Actions（持续集成）运行测试或在生产环境排查问题。

### D. 隐私合规检查

- 启用 GitHub 的 **Secret Scanning（密钥扫描）** 功能。如果有人不小心将 API Key（接口密钥）写入代码并提交，GitHub 会立即发出警告并拦截。
