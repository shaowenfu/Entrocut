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

## 真实桌面导入主链（2026-04 更新）

当前素材导入口径已经收敛为：

1. `create_project` 只创建空 `project + edit_draft`
2. `assets:import` 才是唯一真实素材入口
3. Electron 侧选择目录后，先在 Main Process 扫描视频文件，再以 `files[path]` 提交给 `core`
4. `retrieval_ready` 只由真实切分 + 向量写入成功派生

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

1. `chat` 主链已具备 `retrieve / inspect / patch / preview` 真实执行能力，但 `planner` 质量和长链路稳定性还需继续优化
2. `preview / export` 已切到统一 `RenderPlan` 和真实渲染，实现了可播放产物，但编码参数与性能策略仍是后续优化点
3. 前端已接入 `agent.step.updated` 时间线与 `preview.completed`，但细化交互（如 stale preview 提示、步骤详情折叠）仍可增强
4. `credits / BYOK` 仍需要更系统的端到端验证与真实上游兼容性核查

所以当前更准确的描述是：

`MVP 核心闭环已成立，接下来进入质量、性能与策略层面的持续打磨。`

## 当前项目结构

```text
Entrocut/
├─ .github/             # 仓库级自动化配置入口，集中放置 CI/CD、镜像同步、清理等工作流
│  └─ workflows/        # GitHub Actions 工作流定义目录，负责构建、部署与镜像维护
├─ client/              # 桌面端表现层，提供 Electron 壳、React 界面和前端编排逻辑
│  ├─ main/             # Electron 主进程层，负责窗口生命周期、系统能力和本地 IPC 桥接
│  ├─ public/           # 静态资源目录，放置图标、公开可直接访问的基础资源
│  ├─ src/              # 前端业务源码根目录，承载页面、状态、服务与 Agent 协作逻辑
│  │  ├─ agent/         # 前端侧智能体编排层，负责上下文组装、执行循环和工具调度
│  │  ├─ components/    # 可复用 UI 组件集合，沉淀界面公共能力，减少页面重复实现
│  │  ├─ contracts/     # 前后端契约定义区，沉淀类型、接口形状和消息边界
│  │  ├─ mocks/         # 本地模拟数据与假工作区，用于无后端或离线场景下的前端联调
│  │  ├─ pages/         # 页面级容器组件，负责组合模块并承接路由或视图级状态
│  │  ├─ services/      # 前端服务层，封装 HTTP、Electron 通道、健康检查和媒体注册等能力
│  │  ├─ store/         # 全局状态管理层，基于 Zustand 维护认证、工作区与启动页状态
│  │  ├─ styles/        # 全局样式与设计令牌目录，集中管理主题变量和页面级样式片段
│  │  └─ utils/         # 纯工具函数目录，放置与 UI 无关的会话与数据处理辅助逻辑
│  ├─ build/            # 桌面端构建资产目录，保存打包阶段使用的图标和发布资源
│  └─ release/          # 桌面端发布产物目录，保存本地构建后可分发的安装包或解包结果
├─ core/                # 本地权威引擎层，负责素材处理、Agent 运行和项目状态的本地闭环
│  ├─ routers/          # 本地 HTTP 路由适配层，把外部请求映射到核心业务能力
│  ├─ scripts/          # 核心层辅助脚本目录，放置构建、打包或维护性命令
│  └─ tests/            # 核心层测试目录，覆盖上下文工程、素材处理与服务集成链路
├─ server/              # 云端服务层，负责鉴权、代理、向量检索和运行时防护
│  ├─ app/              # 服务器应用主体目录，按分层架构组织 API、服务、存储与共享工具
│  │  ├─ api/           # API 接入层，统一承接外部请求并向下分发到业务实现
│  │  │  └─ routes/     # 具体路由集合，按业务域拆分鉴权、资源、会话和运行时接口
│  │  ├─ bootstrap/     # 应用启动与装配层，负责依赖注入、生命周期、中间件与异常处理
│  │  ├─ core/          # 服务底座层，放置配置、错误模型、运行时守卫和可观测性基础设施
│  │  ├─ repositories/  # 数据访问层，封装认证会话、本地或云端持久化对象的读写
│  │  ├─ schemas/       # 数据契约层，定义请求、响应与内部传输对象的结构化模型
│  │  ├─ services/      # 业务服务层，承载检索、配额、鉴权和网关转发等核心逻辑
│  │  │  ├─ auth/       # 鉴权子域，处理 OAuth、令牌、用户与辅助工具
│  │  │  └─ gateway/    # 网关子域，处理代理转发、流式传输、模型路由和计费
│  │  └─ shared/        # 共享工具层，放置跨模块复用的无状态公共方法
│  └─ tests/            # 服务器测试目录，覆盖路由、网关、向量服务与启动流程
├─ scripts/             # 仓库级脚本目录，提供启动、冒烟测试、鉴权令牌签发和回归入口
├─ logs/                # 运行日志目录，收集调试、部署与测试过程中的输出记录
├─ temp/                # 临时工作目录，放置一次性中间文件和短生命周期产物
```

## 当前推荐阅读路径

如果你要快速重新进入项目，建议按这个顺序看：

1. [docs/README.md](./docs/README.md)
2. [docs/editing/01_edit_draft_schema.md](./docs/editing/01_edit_draft_schema.md)
3. [docs/store/01_core_api_ws_contract.md](./docs/store/01_core_api_ws_contract.md)
4. [docs/agent_runtime/README.md](./docs/agent_runtime/README.md)
5. [docs/server/README.md](./docs/server/README.md)
6. [docs/develop_diary/2026-03-24_project_recap_and_pause_journal.md](./docs/develop_diary/2026-03-24_project_recap_and_pause_journal.md)
7. [docs/store/02_local_data_storage_architecture.md](./docs/store/02_local_data_storage_architecture.md)
8. [docs/develop_diary/2026-03-29_server_branch_pr_merge_journal.md](./docs/develop_diary/2026-03-29_server_branch_pr_merge_journal.md)

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
npm run electron:dev
```

### 手动启动 core

```bash
cd core
# 第一次需要创建虚拟环境时执行
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


## 桌面端一体化发布进展（2026-04-13）

当前仓库已经落地桌面端 `core supervisor` 最小链路：

1. `core` 可通过 `PyInstaller` 打出 `core-dist/` 可执行目录。
2. Electron Main 会在应用启动时自动拉起本地 `core`，并做 `/health` 探活。
3. Main 通过 `preload + IPC` 向 Renderer 暴露运行态 `core base url`。
4. Renderer 在 `core ready` 前展示桌面初始化页，失败时展示错误态。

对齐文档：

- [docs/tasks/2026-04-12_desktop_local_core_packaging_task.md](./docs/tasks/2026-04-12_desktop_local_core_packaging_task.md)
- [docs/client/01_electron_build_and_release.md](./docs/client/01_electron_build_and_release.md)
