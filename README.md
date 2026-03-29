# EntroCut Monorepo

`EntroCut` 当前处于 `MVP` 重构与 `editing agent（剪辑智能体）` 主骨架收口阶段。

这不是一个“已经产品化”的仓库，而是一个方向已经比较清楚、但核心 `agent loop` 仍在继续落地的系统。

## 当前项目的一句话定位

`EntroCut` 想做的是一个 `Chat-to-Cut（对话到剪辑）` 系统：

1. 用户通过自然语言表达目标
2. 系统围绕 `EditDraft` 形成结构化剪辑草案
3. 后续再通过局部选择、检索、判定、补丁和预览，持续收敛结果

## 当前三端分工

### 1. `client/`

技术栈：`Electron + React + Vite + Zustand`

当前职责：

1. `Launchpad / Workspace` 界面与状态同步
2. 调用本地 `core` 契约
3. 承载一套前端侧 `agent runtime` 原型骨架

### 2. `core/`

技术栈：`Python + FastAPI`

当前职责：

1. 本地项目与 `EditDraft` 状态管理
2. `Client -> Core` 本地契约落点
3. `planner-first` 的 `chat` 主链骨架
4. `WebSocket event stream` 推送

### 3. `server/`

技术栈：`Python + FastAPI`

当前职责：

1. `Core -> Server` 云端能力网关
2. `OpenAI-compatible` `completion` 代理
3. `vectorize / retrieval / inspect` 专用工具接口
4. 鉴权、能力探测与错误语义稳定化

当前 `server` 分支额外已经并入的能力点：

1. `Google + GitHub OAuth`
2. `client -> core -> server` 登录态同步链
3. `credits_balance` 用户字段及前端展示入口
4. `model selection + BYOK routing` 配套参数透传

## 当前核心数据模型

系统当前围绕 `EditDraft` 工作，而不是围绕展示型 `Storyboard` 工作。

基本层次是：

1. `Asset`
2. `Clip`
3. `Shot`
4. `Scene`
5. `EditDraft`

当前统一口径：

1. `clip` 是分析/检索单元
2. `shot` 是最小可编辑语义单元
3. `scene` 是可选工作分组层
4. 最终执行语义以 `EditDraft.shots` 为准

## 当前整体进度

### 已经比较明确的部分

1. 最小 `Launchpad -> Workspace -> import -> chat -> export -> preview` 闭环已经跑通过
2. `EditDraft` 已经成为统一事实源
3. `agent runtime` 的五层骨架已经讨论清楚并大部分文档化：
   - `State`
   - `Planner`
   - `Tool`
   - `Memory / Context`
   - `Execution Loop`
4. `retrieve / inspect / patch / preview` 的工具边界已经收口
5. `server` 侧的 `planner / vectorize / retrieval / inspect` 契约和实现已经开始成型
6. `server` 分支已经回收两条历史能力线：`GitHub OAuth` 与 `credits/BYOK`

### 当前仍在收口的部分

1. `core /chat` 还停在 `planner-first` 骨架阶段
2. `planner -> tool execution -> replanning` 的真实 `agent loop` 还没有在 `core` 里彻底落地
3. `retrieve / inspect` 的真实 `Core -> Server` 接入还需要继续按新契约推进
4. `credits / BYOK` 还需要更系统的端到端验证与真实上游兼容性核查

所以现在最准确的描述不是“功能缺很多”，而是：

`系统主方向已经基本确定，但核心 agent 执行闭环仍在实现中。`

## 当前推荐阅读路径

如果你要快速重新进入项目，建议按这个顺序看：

1. [docs/README.md](./docs/README.md)
2. [docs/editing/01_edit_draft_schema.md](./docs/editing/01_edit_draft_schema.md)
3. [docs/contracts/01_core_api_ws_contract.md](./docs/contracts/01_core_api_ws_contract.md)
4. [docs/agent_runtime/README.md](./docs/agent_runtime/README.md)
5. [docs/server/README.md](./docs/server/README.md)
6. [docs/develop_diary/2026-03-29_server_branch_pr_merge_journal.md](./docs/develop_diary/2026-03-29_server_branch_pr_merge_journal.md)
7. [docs/develop_diary/2026-03-24_project_recap_and_pause_journal.md](./docs/develop_diary/2026-03-24_project_recap_and_pause_journal.md)

## 当前关键接口面

### Core

当前真实入口主要包括：

1. `GET /health`
2. `GET /api/v1/runtime/capabilities`
3. `GET /api/v1/projects`
4. `POST /api/v1/projects`
5. `GET /api/v1/projects/{project_id}`
6. `POST /api/v1/projects/{project_id}/assets:import`
7. `POST /api/v1/projects/{project_id}/chat`
8. `POST /api/v1/projects/{project_id}/export`
9. `GET /api/v1/projects/{project_id}/events` (`WebSocket`)

### Server

当前重点接口包括：

1. `POST /v1/chat/completions`
2. `POST /v1/assets/vectorize`
3. `POST /v1/assets/retrieval`
4. `POST /v1/tools/inspect`
5. `GET /api/v1/runtime/capabilities`

更详细的字段级契约，请直接看 `docs/server/`。

## 本地启动

### 一键启动

```bash
./scripts/dev_up.sh
```

### 手动启动 client

```bash
cd client
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### 手动启动 core

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

### 手动启动 server

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## 当前非目标

当前仓库明确不追求这些事情：

1. 不做传统 `timeline editor（时间线编辑器）`
2. 不提前接入复杂精剪、特效、协作等重能力
3. 不让 `Storyboard` 重新变回事实源
4. 不用一堆固定规则去“教 AI 怎么剪”

当前最重要的原则仍然是：

`把脚手架收缩到基础设施层，把决策自由留给模型。`
