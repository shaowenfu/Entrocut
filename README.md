# EntroCut Monorepo

`EntroCut` 当前处于 `MVP` 重构与 `editing agent（剪辑智能体）` 主骨架收口阶段。

这不是一个“已经产品化”的仓库，而是一个方向已经比较清楚、但核心 `agent loop` 仍在继续落地的系统。

## 当前项目的一句话定位

`EntroCut` 想做的是一个 `Chat-to-Cut（对话到剪辑）` 系统：

1. 用户通过自然语言表达目标
2. 系统围绕 `EditDraft` 形成结构化剪辑草案
3. 后续再通过局部选择、检索、判定、补丁和预览，持续收敛结果

## 出发点
视频剪辑 的本质，不是“操作时间线”，而是从一堆原始时空片段里，选择、排序、裁切、组织出一个能表达意图的观看序列。

系统最底层不会变的真理：
1. 原始世界里有 media asset（媒体素材）
2. 素材里有可被理解和复用的 candidate unit（候选片段）
3. 用户有一个想表达的 intent（意图）
4. 剪辑过程就是不断把“候选片段集合”收敛成“满足意图的最终序列”

从这些真理往上推，系统是在做：intent -> selection -> arrangement -> refinement -> export

## 剪辑过程的本质

如果继续往下压缩，剪辑过程本质上只是在反复做 4 件事：

1. `select（选）`
   - 从素材里找可用内容
2. `compose（排）`
   - 决定顺序、时长、分组和衔接
3. `evaluate（判）`
   - 判断当前草案是否更接近目标
4. `revise（改）`
   - 做局部替换、缩短、延长、重排和补镜头

所以一个真正可工作的 `editing agent（剪辑智能体）`，最小也必须能支持：

`选 -> 排 -> 判 -> 改`

当前项目里收口出来的高层工具边界，本质上也正是在服务这 4 个动作：

1. `retrieve` 解决“选”
2. `inspect` 解决“判”
3. `patch` 解决“改”
4. `preview` 解决“判 + 对人展示”

## 系统目标

`EntroCut` 的目标不是做一个传统 `timeline editor（时间线编辑器）`，也不是一次性替代专业剪辑师。

更准确的说法是：

`帮助用户通过自然语言，持续把一个模糊剪辑目标收敛成一个可执行的 EditDraft。`

所以系统真正要做的不是“一次性生成视频”，而是：

`iterative convergence（迭代收敛）`

这也决定了：

1. 最重要的事实源必须是 `EditDraft`
2. 最重要的运行能力必须是 `agent loop`
3. 最重要的工程问题必须是 `context engineering（上下文工程）`

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

## 数据存储方向

当前仓库的 `core` 仍以 `in-memory state（内存状态）` 为主，这适合原型期。

但从桌面应用的长期最佳实践看，本项目的数据层方向已经明确：

### 本地

1. `SQLite`
   - 作为本地权威业务数据库
   - 保存 `project / asset / clip / edit_draft / shot / scene / chat_turn / task / runtime state`
2. `File System（文件系统）`
   - 保存原始媒体、预览文件、导出文件、缩略图和其它中间产物
3. `Keychain / Credential Manager（系统安全存储）`
   - 保存 `access_token / refresh_token / third-party secrets`

### 云端

1. `MongoDB Atlas`
   - 只做同步、账号和云元数据
   - 不作为桌面端本地事实源

这意味着后续最重要的数据层演进不是给 `client` 增加更多本地 store，而是：

`把 core 从 in-memory state server 升级成 SQLite-backed local backend。`

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

### 当前仍在收口的部分

1. `core /chat` 还停在 `planner-first` 骨架阶段
2. `planner -> tool execution -> replanning` 的真实 `agent loop` 还没有在 `core` 里彻底落地
3. `retrieve / inspect` 的真实 `Core -> Server` 接入还需要继续按新契约推进

所以现在最准确的描述不是“功能缺很多”，而是：

`系统主方向已经基本确定，但核心 agent 执行闭环仍在实现中。`

## 当前推荐阅读路径

如果你要快速重新进入项目，建议按这个顺序看：

1. [docs/README.md](./docs/README.md)
2. [docs/editing/01_edit_draft_schema.md](./docs/editing/01_edit_draft_schema.md)
3. [docs/contracts/01_core_api_ws_contract.md](./docs/contracts/01_core_api_ws_contract.md)
4. [docs/agent_runtime/README.md](./docs/agent_runtime/README.md)
5. [docs/server/README.md](./docs/server/README.md)
6. [docs/develop_diary/2026-03-24_project_recap_and_pause_journal.md](./docs/develop_diary/2026-03-24_project_recap_and_pause_journal.md)
7. [docs/contracts/02_local_data_storage_architecture.md](./docs/contracts/02_local_data_storage_architecture.md)

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
