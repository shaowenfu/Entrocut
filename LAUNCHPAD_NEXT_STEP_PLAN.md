# Launchpad Next Step Plan

## 1. 当前落地状态（截至 2026-03-05）

1. 已建立 `Zustand（状态管理）` 主体：
   - `recentProjects`、`activeWorkspaceId`、`activeWorkspaceName`、`isLoadingProjects`、`isImporting`、`isCreating`、`isThinking`、`lastError`。
   - Action：`fetchRecentProjects`、`importLocalFolder`、`createEmptyProject`、`createProjectFromPrompt`、`openWorkspace`。
2. `LaunchpadPage（启动台页面）` 已切换为 `Store-driven（状态驱动）`：
   - 页面只触发 Action，展示 Store 数据。
   - 搜索使用 `local state（局部状态）` + `derived list（派生列表）`。
3. `App.tsx` 已改为监听 `activeWorkspaceId` 自动从 Launchpad 切换到 Workspace。
4. `Electron bridge（桥接层）` 已补类型声明：`window.electron.showOpenDirectory`。
5. 编译状态：`npm run typecheck`、`npm run build` 均通过。

## 2. 设计边界（必须保持）

1. 页面层只做两件事：
   - 触发动作（Action）。
   - 渲染状态（State）。
2. 所有副作用必须收敛到 Store 或 Service：
   - `API request（接口请求）`。
   - `Electron dialog（系统弹窗）`。
   - 错误映射与重试。
3. 统一错误语义：`code + message + cause`，禁止静默吞错。

## 3. 下一阶段开发任务（按优先级）

### P0: 打通 Core Contract（本地端到端最小闭环）

1. 在 `core` 落地以下接口并替换占位 `501`：
   - `GET /api/v1/projects`
   - `POST /api/v1/projects`
   - `POST /api/v1/projects/import`
2. 固化响应 Schema（最小集合）：
   - `ProjectMeta` 列表字段与创建返回字段（`project_id`, `title`）。
3. 启动台验证路径：
   - `fetchRecentProjects -> recentProjects`。
   - `createEmptyProject -> activeWorkspaceId`。
   - `importLocalFolder -> activeWorkspaceId`。

### P1: 打通 Server Chat Trigger（Prompt 到 AI 的异步握手）

1. 在 `server` 完成 `POST /api/v1/chat` 的最小可用实现（可先返回 `accepted` + `job_id`）。
2. `createProjectFromPrompt` 保持“先跳转后思考”语义：
   - 创建项目成功后立即设置 `activeWorkspaceId`。
   - 并发触发 `chat`；在 Store 中维护 `isThinking`。
3. 约定失败策略：
   - 项目创建成功但 `chat` 失败时，不回滚项目；只更新 `lastError`。

### P1: Electron Bridge 实装

1. 在 `client/main/preload.ts` 暴露：
   - `showOpenDirectory(): Promise<string | null>`。
2. 在 `client/main/main.ts` 用 `dialog.showOpenDialog` 实现目录选择。
3. 保持 `contextIsolation` 开启，不向 Renderer 暴露 Node 原始能力。

### P2: Workspace 联动（从“跳转”升级为“可消费项目”）

1. 新建 `workspace slice` 或 `project slice`：
   - 按 `activeWorkspaceId` 拉取素材、分镜、会话。
2. `WorkspacePage` 移除本地 `mock`：
   - `assets/clips/storyboard/chatTurns` 全量来自 Store。
3. 建立 `launchpad -> workspace` 的数据契约：
   - 进入 Workspace 时必须存在 `activeWorkspaceId`。

### P2: 可验证性与回归保护

1. Store 单测（至少覆盖）：
   - 成功路径：列表加载/创建/导入/Prompt。
   - 失败路径：Core 失败、Server 失败、Bridge 缺失、用户取消。
2. 增加最小 `E2E（端到端）` 脚本：
   - 启动三端后，验证启动台核心 5 功能主路径。

## 4. 建议的代码结构落地

1. `client/src/store/useLaunchpadStore.ts`：只保留状态机与 Action。
2. `client/src/services/launchpadApi.ts`：封装 Core/Server HTTP 调用。
3. `client/src/services/electronBridge.ts`：封装 `window.electron` 调用与兼容分支。
4. `client/src/types/launchpad.ts`：集中放 `Schema（契约类型）`。

## 5. Done Definition（阶段完成标准）

1. Launchpad 五个核心功能不依赖任何页面内 `mock`。
2. 页面中不直接出现 `fetch(...)` 与 `window.electron...`。
3. `activeWorkspaceId` 成为唯一跳转判据。
4. 所有失败路径可见、可分支处理、可日志追踪。
