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

我们将配置两个主要的流水线（Workflows）：

### A. 客户端构建 (Client CD)

- **触发条件**：当 `main` 分支有新的 `tag` (如 `v1.0.0`) 时。
- **任务**：
    1. 安装 Node.js 和 Python 环境。
    2. 在 Windows/macOS 虚拟运行环境下打包 Electron。
    3. 利用 `electron-builder` 生成 `.exe` 或 `.dmg` 安装包。
    4. **产物**：自动上传至 GitHub Releases 供用户下载。

### B. 后端部署 (Server CD - 阿里云)

- **触发条件**：推送代码至 `main` 分支。
- **任务流**：
    1. **Build**: 构建服务端 Docker 镜像。
    2. **Push**: 将镜像推送到 **阿里云容器镜像服务 (ACR)**。
    3. **Deploy**: 远程登录阿里云服务器 (ECS)，执行 `docker-compose pull` 并重启服务。

## 4. 部署至阿里云的详细步骤

### 准备工作

1. **阿里云端**：
    - 开通 **ACR (容器镜像服务)**，创建命名空间和仓库。
    - 准备一台 **ECS 服务器**，安装 Docker 和 Docker-compose。
2. **GitHub 端**：
    - 在仓库设置中进入 `Settings > Secrets and variables > Actions`，添加以下 **Secrets**（保护敏感信息）：
        - `ALB_ACR_REGISTRY`: 阿里云镜像地址。
        - `ALB_ACR_USERNAME`: 镜像仓库登录名。
        - `ALB_ACR_PASSWORD`: 镜像仓库登录密码。
        - `SERVER_SSH_HOST`: ECS 服务器公网 IP。
        - `SERVER_SSH_KEY`: 用于登录服务器的私钥。

### 自动部署示例逻辑 (YAML)

```
# 逻辑简述：
# 1. 登录阿里云 Docker 仓库
# 2. 构建并推送 server 镜像
# 3. 通过 SSH 登录 ECS 更新容器

```

## 5. 其它协作细节补充

### A. 环境变量管理 (.env)

- **禁止将 `.env` 文件提交到 GitHub**（在 `.gitignore` 中忽略）。
- 团队内共享一份 `.env.template` 模板文件，列出所有需要的 Key（如 `DASHSCOPE_API_KEY`），但值留空，由成员自行在本地填充。

### B. Issue 与项目看板: linear

### C. 结构化日志 (Structured Logging)

- 要求算法端 (Python) 和服务端 (FastAPI) 使用统一的日志格式（如 JSON Log），方便通过 GitHub Actions 运行测试或在生产环境排查问题。

### D. 隐私合规检查

- 启用 GitHub 的 **Secret Scanning** 功能。如果有人不小心将 API Key 写入代码并提交，GitHub 会立即发出警告并拦截。