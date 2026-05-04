# EntroCut Client

`client/` 是 EntroCut 的桌面前端与 Web 调试前端，当前技术栈是 `Electron + React + Vite + Zustand`。它不是单纯页面壳，而是承担了桌面启动、本地媒体接入、项目工作台、认证状态、`core` API（应用程序接口）同步与运行状态可视化。

当前更准确的定位是：

```text
Client = Electron Desktop Shell（桌面壳层）
       + React Renderer（交互界面）
       + Zustand State Machine（前端状态机）
       + Core API Adapter（core 契约适配层）
```

## 核心目录导航

```text
client/
├── main/                              # Electron Main Process（主进程）
│   ├── main.ts                        # 桌面入口：窗口、deep link、secure store、IPC 注册
│   ├── preload.ts                     # Preload Bridge：向 Renderer 暴露受控 window.electron API
│   ├── coreSupervisor.ts              # 托管本地 core：动态端口、启动、health check、退出回收
│   ├── fileScanner.ts                 # 本地视频/目录扫描：返回结构化 media.files[] 给 Renderer
│   └── localMediaProtocol.ts          # entrocut-media:// 协议：本地视频预览与 range streaming
│
├── src/                               # React Renderer Process（渲染进程）
│   ├── App.tsx                        # 应用总入口：core ready gate、auth deep link、页面切换
│   ├── main.tsx                       # React 挂载入口
│   ├── electron.d.ts                  # window.electron 类型声明
│   │
│   ├── pages/                         # 页面级工作流
│   │   ├── LaunchpadPage.tsx          # 项目入口：最近项目、创建项目、拖拽/选择素材
│   │   └── WorkspacePage.tsx          # 剪辑工作台：素材、clips、storyboard、chat、preview、export
│   │
│   ├── store/                         # Zustand Store（状态机）
│   │   ├── useLaunchpadStore.ts       # 项目列表、创建/导入、进入 workspace
│   │   ├── useWorkspaceStore.ts       # workspace snapshot、events、chat、tasks、export、agent steps
│   │   └── useAuthStore.ts            # 登录态、token、模型偏好、Platform/BYOK 路由偏好
│   │
│   ├── services/                      # 外部边界适配层
│   │   ├── coreClient.ts              # core HTTP/WebSocket API client 与 TypeScript schema
│   │   ├── httpClient.ts              # requestJson、token 注入、错误归一化
│   │   ├── authClient.ts              # server auth API、OAuth login session、refresh token
│   │   ├── electronBridge.ts          # Renderer 侧 Electron bridge 封装与媒体选择 fallback
│   │   ├── localMediaRegistry.ts      # 本地媒体注册、预览 URL、thumbnail 生成
│   │   └── health.ts                  # 基础 health 检查
│   │
│   ├── components/                    # 可复用 UI 组件
│   │   ├── account/                   # AccountMenu：登录、登出、模型偏好
│   │   ├── icons/                     # BrandIcon 等品牌图标
│   │   └── ui/                        # Button/Input/Card/StatusBadge 等基础组件
│   │
│   ├── styles/                        # 页面与设计 token
│   │   ├── tokens.css                 # 颜色、间距等 CSS token
│   │   ├── launchpad.css              # Launchpad 页面样式
│   │   └── workspace.css              # Workspace 页面样式
│   │
│   ├── utils/                         # session 等轻量工具
│   └── contracts/                     # 预留契约目录；当前没有实质文件
│
├── public/                            # Vite public assets（favicon、icon）
├── build/                             # electron-builder buildResources（桌面构建资源）
├── package.json                       # scripts、dependencies、Electron/Vite 构建命令
├── vite.config.ts                     # Vite 配置
├── tsconfig.json                      # TypeScript 配置
├── electron-builder.yml               # 桌面安装包配置与 core-dist 资源打包
└── index.html                         # Renderer HTML 入口
```

说明：`dist/`、`dist-electron/`、`release/`、`node_modules/` 是构建或依赖产物，不属于核心源码导航。

## 当前已落地能力

### 1. Launchpad（项目入口）

`LaunchpadPage` 已经接入真实项目流：

- 拉取最近项目：`listProjects`
- 创建空项目或按 prompt（提示词）创建项目：`createProject`
- 支持拖拽视频文件进入项目
- 在 Electron 环境下通过统一 `Browse Media` 入口选择视频文件或媒体目录；目录会递归扫描视频
- 创建后会预热 `WorkspaceStore`，再进入工作台

浏览器模式只能拿到受限的 `File` 信息；桌面模式通过 `Electron IPC`（进程间通信）拿到本地路径，并统一映射为 `media.files[]` 提交给 `core`。

### 2. Workspace（剪辑工作台）

`WorkspacePage` 当前围绕 `core` 返回的 `workspace snapshot` 工作，主要功能包括：

- 展示 `assets / clips / storyboard`
- 预览素材或导出的 draft preview
- 上传/导入新素材
- 发送 chat 请求，并携带当前 scene selection（场景选择上下文）
- 展示 `core` 的 active tasks（运行中任务）
- 订阅项目 WebSocket events（事件流）
- 展示 `agent.step.updated` 执行过程
- 触发 export，并消费 `export.completed`
- 消费 `preview.completed`，优先播放 draft preview；本地源视频预览走 `entrocut-media://`

当前页面中的 `storyboard` 是显示层概念，真正的事实源是 `editDraft`：

```text
core.edit_draft.assets  -> Workspace assets view
core.edit_draft.clips   -> Workspace clips view
core.edit_draft.scenes  -> Storyboard view（派生视图）
core.edit_draft.shots   -> Scene 与 clip 的连接关系
```

也就是说，`storyboard` 不应被理解为新的业务契约，它只是 `EditDraft.scenes` 的 UI 投影。

### 3. Core 连接与桌面托管

桌面端现在已经有 `core supervisor`：

- 开发态默认从仓库 `core/` 拉起本地服务
- 自动分配本地端口
- 注入 `CORE_PORT` 与 `ENTROCUT_APP_DATA_ROOT`
- 轮询 `/health`，ready 后通过 IPC 通知 Renderer
- 应用退出时回收 core 进程
- 发布态从 `resources/core-dist/entrocut-core(.exe)` 拉起内置 core

开发态可通过环境变量切换为外部 core：

```bash
ENTROCUT_SKIP_MANAGED_CORE=1 VITE_CORE_BASE_URL=http://127.0.0.1:8000 npm run electron:dev
```

此时 Electron 不再托管 core，而是等待 `VITE_CORE_BASE_URL` 的 `/health` 可用。

### 4. 本地媒体接入

桌面媒体链路当前是：

```text
Electron Main Process
  -> fileScanner.ts 扫描文件/目录
  -> preload.ts 暴露受控 API
  -> electronBridge.ts 归一化输入
  -> coreClient.toMediaReference()
  -> core /api/v1/projects 或 /assets:import
```

`folderPath` 只保留兼容语义；真实 ingest（导入）主契约已经转为 `media.files[]`。这能让 `core` 拿到明确的 `name/path/size_bytes/mime_type`，避免让后端再猜测目录内容。

本地预览走 `entrocut-media://` 自定义协议，支持视频 `range request`，避免 Renderer 直接暴露任意文件系统能力。

### 5. Auth（认证）与模型路由偏好

当前前端已有认证状态管理：

- 支持 Google/GitHub login session
- Electron 下支持 deep link 回调：`entrocut://auth/callback`
- 开发态支持 polling login mode
- refresh token 在 Electron 下优先进入 secure store
- 登录态会同步到 `core` 的 `/api/v1/auth/session`

模型偏好在 `useAuthStore` 中保存，包括：

- `selectedModel`
- `routingMode`: `Platform` 或 `BYOK`
- `byokKey`
- `byokBaseUrl`

发送 chat 时会通过 header 把 routing mode（路由模式）传给 `core`。

### 6. Agent 边界

Agent 编排事实源已经收敛到 `core`：

- planner context（规划上下文）由 `core/context.py` 派生
- planner/tool loop（规划与工具循环）由 `core/agent.py` 执行
- `read / retrieve / inspect / patch / preview` 的 gating（能力门控）与执行在 `core`
- `client` 只负责发送 chat、传递 selection target（选择目标）、展示 `agent.step.updated` 可视化事件

因此 `client/src/agent` 前端原型层已删除，避免 Renderer 绕过 `core` 自行编排 agent 或修改 draft。

## 与 Core 的主要 API 契约

`src/services/coreClient.ts` 是前端与 `core` 的主要边界，目前覆盖：

- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/assets:import`
- `POST /api/v1/projects/{project_id}/chat`
- `POST /api/v1/projects/{project_id}/export`
- `WS /api/v1/projects/{project_id}/events`
- `POST /api/v1/auth/session`
- `DELETE /api/v1/auth/session`

前端依赖的核心数据结构也集中在这里定义，例如 `CoreWorkspaceSnapshot`、`CoreEditDraft`、`CoreTask`、`CoreProjectRuntimeState`、`CoreProjectCapabilities`、`CoreAgentStepItem`。

## 本地运行

安装依赖：

```bash
cd client
npm install
```

Web 调试模式：

```bash
npm run dev:web
```

桌面联调模式：

```bash
npm run electron:dev
```

常用检查：

```bash
npm run typecheck
npm run build
```

桌面打包：

```bash
npm run electron:build-all
```

平台单独打包：

```bash
npm run electron:build:linux
npm run electron:build:mac
npm run electron:build:win
```

打包命令会先执行 `core:build-desktop`，再构建 Renderer、Main/Preload，并通过 `electron-builder` 把 `../core/dist/core-dist` 放入桌面应用资源。

## Electron 调试口径

`Electron` 调试需要区分两个进程：

1. `Main Process（主进程）`
   - 对应 `client/main/main.ts` 和 `client/main/preload.ts`
   - 使用 VS Code 配置：`Debug Client (Electron)`

2. `Renderer Process（渲染进程）`
   - 对应 `client/src/**/*.ts(x)`，例如 `src/services/authClient.ts`、`src/store/useAuthStore.ts`、`src/App.tsx`
   - 使用 VS Code 配置：`Attach Client Renderer (Electron/Vite)`

正确操作顺序：

1. 先彻底停止旧的 `npm run electron:dev`、旧 `Electron` 窗口和旧 VS Code debug session
2. 在 VS Code `Run and Debug` 中启动 `Debug Client (Electron)`
3. 等 `Electron` 窗口出现，并确认 `Vite` 页面已经加载
4. 再启动 `Attach Client Renderer (Electron/Vite)`
5. 此时再在 `client/src/**/*.ts(x)` 中打断点

也可以直接使用 VS Code compound（组合调试）：

```text
Debug Electron Client (Main + Renderer)
```

典型断点位置：

- Main：`main/main.ts`、`main/coreSupervisor.ts`、`main/fileScanner.ts`
- Renderer：`src/App.tsx`、`src/store/useWorkspaceStore.ts`、`src/services/authClient.ts`

如果 `client/src/**/*.ts(x)` 的断点不生效，通常是把 Renderer 断点挂到了 Main debug session。Renderer 需要 attach 到 Vite 页面对应的 Chromium 进程。

## 当前非目标

当前 `client` 明确不承担这些事情：

- 不实现传统多轨时间线编辑器
- 不把 `storyboard` 作为独立业务事实源
- 不让 Renderer 获得任意文件系统访问权
- 不在前端保留独立 `agent runtime` 或本地 tool loop
- 不在 UI 层绕过 `core` 直接修改持久化剪辑状态
- 不在当前阶段扩展复杂 IPC 文件管理能力

## 后续最值得推进的方向

如果继续推进 `client`，优先级最高的不是继续堆页面装饰，而是收紧契约和交互事实源：

1. 让 Workspace 交互更明确围绕 `editDraft / selection / chat target` 工作。
2. 逐步减少页面代码对派生 `storyboard` 字段的直接依赖。
3. 把 `coreClient.ts` 中的 schema 与后端契约保持同步，避免 UI 自造字段语义。
4. 为 `WorkspaceStore` 的事件归约逻辑补最小回归测试，尤其是 `snapshot / task / preview / export / agent step` 的组合事件。
5. 继续保持 agent 编排只在 `core`，client 只展示过程与结果。
