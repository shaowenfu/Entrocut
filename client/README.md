# Client

`client/` 是当前项目的桌面前端壳层，技术栈是 `Electron + React + Vite + Zustand`。

它现在已经不是“只有页面壳”的状态，而是承担了三类真实职责：

1. `Launchpad / Workspace` 的界面交互
2. 围绕 `core` 本地契约的状态同步
3. 一套前端侧 `agent runtime` 原型骨架

## 当前定位

当前 `client` 的真实角色是：

`交互表现层 + 本地状态机 + agent runtime 原型试验场`

它不是最终产品形态，但也不再只是空壳。

## 当前真实能力

### 页面与状态

1. `LaunchpadPage`
   - 最近项目
   - 新建项目
   - 选择媒体并进入 `Workspace`

2. `WorkspacePage`
   - 读取 `workspace snapshot`
   - 展示 `assets / clips / storyboard(view)` 与聊天记录
   - 上传素材
   - 发送 chat
   - 导出项目
   - 订阅 `project events`

3. `Zustand` 状态层
   - `useLaunchpadStore.ts`
   - `useWorkspaceStore.ts`

### 运行时骨架

前端当前已经落下了 `agent runtime` 的一套原型模块：

1. `sessionRuntimeState.ts`
2. `contextAssembler.ts`
3. `plannerOutput.ts`
4. `plannerRunner.ts`
5. `llmPlannerRunner.ts`
6. `toolExecutor.ts`
7. `executionLoop.ts`

这套骨架当前主要用于：

1. 代码化 `State / Planner / Tool / Context / Execution Loop`
2. 在前端侧验证运行时对象和契约边界

需要强调：

`这套前端 agent runtime 目前仍然是原型实验层，不代表最终 planner 和 tool 执行都会常驻在 client。`

## 当前事实源与显示层关系

前端现在围绕 `EditDraft` 工作。

当前页面里仍然展示 `storyboard`，但它的语义已经被收窄为：

`EditDraft.scenes` 的展示视图

也就是说：

1. 真正的剪辑事实源是 `editDraft`
2. `storyboard` 只是兼容现有 UI 的派生显示层

## 当前与 core 的交互

前端主要通过这些服务模块和 `core` 对话：

1. `services/coreClient.ts`
2. `services/httpClient.ts`
3. `services/authClient.ts`
4. `services/health.ts`

当前关键交互包括：

1. 拉取项目列表
2. 创建项目
3. 初始化 `workspace`
4. 导入素材
5. 发送 chat
6. 订阅 `WebSocket events`
7. 导出项目

## 当前非目标

当前 `client` 明确还不做这些事：

1. 不实现传统时间线编辑器
2. 不提供复杂 `IPC` 文件系统能力扩展
3. 不在前端长期持有真实云端工具执行权威
4. 不把前端 `agent runtime` 试验骨架误认为最终生产实现

## 代码入口

建议先看：

1. [src/App.tsx](./src/App.tsx)
2. [src/pages/LaunchpadPage.tsx](./src/pages/LaunchpadPage.tsx)
3. [src/pages/WorkspacePage.tsx](./src/pages/WorkspacePage.tsx)
4. [src/store/useLaunchpadStore.ts](./src/store/useLaunchpadStore.ts)
5. [src/store/useWorkspaceStore.ts](./src/store/useWorkspaceStore.ts)

如果想理解前端侧 `agent runtime` 原型，再看：

1. [src/agent/sessionRuntimeState.ts](./src/agent/sessionRuntimeState.ts)
2. [src/agent/contextAssembler.ts](./src/agent/contextAssembler.ts)
3. [src/agent/executionLoop.ts](./src/agent/executionLoop.ts)

## 本地启动

```bash
cd client
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

如果需要桌面联调：

```bash
cd client
npm install
npm run electron:dev
```

## 当前最应该做的事

如果继续推进 `client`，当前最值得做的不是继续堆页面细节，而是：

`逐步减少页面对派生 storyboard 视图的依赖，并让前端交互更明确地围绕 selection / editDraft / chat target 工作。`

## 桌面端 Core 托管（新增）

当前 Electron 主进程已经引入 `core supervisor`：

1. 入口模块：`main/coreSupervisor.ts`
2. 负责：动态端口分配、拉起本地 `core`、`/health` 探活、退出回收
3. 通过 `preload + IPC` 向 Renderer 暴露运行时 `core base url`
4. Renderer 启动时会等待 `core ready`，未就绪时显示初始化页

开发态默认行为：

1. `electron:dev` 启动后，Main 会尝试用 `python3 -m uvicorn server:app` 从仓库 `core/` 拉起服务
2. 可通过 `ENTROCUT_SKIP_MANAGED_CORE=1` 跳过托管并连接外部 `VITE_CORE_BASE_URL`

发布态默认行为：

1. Main 从 `process.resourcesPath/core-dist/entrocut-core(.exe)` 拉起内置 core
2. 启动注入 `ENTROCUT_APP_DATA_ROOT=<userData>/core-data` 与动态 `CORE_PORT`
