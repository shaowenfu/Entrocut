# Workspace Next Step Plan

## 1. 目标与边界

1. 目标：打通 `Launchpad（启动台） -> Workspace（工作台）` 的真实业务链路，覆盖 3 种输入情况，并在工作台 `Assets（素材区）` 提供可用的上传入口。
2. 架构边界：页面组件只做 `Trigger Action（触发动作）` 与 `Render State（渲染状态）`；所有副作用放在 `Zustand Store（状态管理）` + `Electron Bridge（桥接层）` + `Service API（接口层）`。
3. 非目标：本阶段不做复杂 `Timeline Editor（时间线编辑器）`、不做多路并发导出、不中断当前 UI 骨架。

## 2. 先对齐三种启动情况

1. 情况 1（只上传视频，不输入指令）
2. 情况 2（只输入指令，不上传视频）
3. 情况 3（既上传视频，也输入指令）

统一入口建议：`startWorkspaceFromLaunchpad(input)`。

输入结构建议：

```ts
type LaunchInput = {
  prompt?: string;
  folderPath?: string;
  files?: File[];
};
```

## 3. 统一状态机（核心）

建议新增 `LaunchWorkflowState（启动流程状态）`，避免在页面写 if-else 业务流：

1. `idle`
2. `project_creating`
3. `media_processing`
4. `indexing`
5. `waiting_for_prompt`
6. `chat_thinking`
7. `ready`
8. `failed`

建议新增 `Workflow Context（流程上下文）`：

```ts
type LaunchWorkflowContext = {
  projectId: string | null;
  projectName: string | null;
  pendingPrompt: string | null;
  hasMedia: boolean;
  mediaProgressText: string | null;
  error: LaunchpadError | null;
};
```

## 4. 三种情况的执行链路

### 4.1 情况 1：只上传视频

1. `LaunchpadPage` 触发 `startWorkspaceFromLaunchpad({ files | folderPath })`。
2. `Store` 创建项目（有目录走 `import`，有文件走 `upload`）。
3. 设置 `activeWorkspaceId`，立即切到 `Workspace`。
4. 自动触发 `core`：开始 `Ingest（切分/抽帧）`。
5. `Ingest` 完成后调用 `server`：`Index Upsert（向量化入库）`。
6. `Workspace` 顶部或素材区显示 `Processing Status（处理中状态）`，结束后转 `ready`。

### 4.2 情况 2：只输入指令

1. `LaunchpadPage` 触发 `startWorkspaceFromLaunchpad({ prompt })`。
2. `Store` 创建空项目，设置 `activeWorkspaceId`，切到 `Workspace`。
3. 立即调用 `server /api/v1/chat`。
4. 发送前在 `prompt` 追加系统提示：`当前无素材，请先引导用户上传素材，并给出可执行下一步。`。
5. `Workspace` 显示 `chat_thinking`，拿到回复后展示 `Decision Card（决策卡片）`。

### 4.3 情况 3：上传视频 + 输入指令

1. 与情况 1 相同，先创建项目并进入 `media_processing`。
2. 将用户 `prompt` 写入 `pendingPrompt`。
3. `Ingest + Index` 全部完成前，不调用 `chat`，UI 显示 `视频处理中`。
4. 处理完成后自动取出 `pendingPrompt` 调 `server /api/v1/chat`。
5. 进入 `chat_thinking`，返回后更新 `storyboard/chat`。

## 5. 工作台上传入口（任务二）

建议在 `Workspace Assets Panel（素材面板）` 放两个入口：

1. `Upload Button（上传按钮）`：点击打开文件选择器（支持多选视频）。
2. `Drop Zone（拖拽区）`：支持拖拽视频文件或目录。

交互策略：

1. 上传动作只触发 `workspaceStore.uploadAssets(files | folderPath)`。
2. 上传成功后自动触发同一条 `Ingest -> Index` 流程。
3. 若当前有 `pendingPrompt`，上传处理完成后自动恢复调用 `chat`。
4. 失败时展示可分支错误（`CORE_INVALID_UPLOAD_FILES`、`NETWORK_ERROR`、`SERVER_VECTOR_UPSERT_FAILED`）。

## 6. 接口契约调整（先最小可用）

### 6.1 Core 侧

1. 保留现有：`POST /api/v1/projects`、`POST /api/v1/projects/import`、`POST /api/v1/projects/upload`。
2. 新增最小 `Ingest` 能力：`POST /api/v1/ingest`（按 `project_id` 处理已挂载素材）。
3. 返回最小 `Clip Payload（片段载荷）`，供 `server` 向量化。
4. 错误码建议补齐：`CORE_INGEST_FAILED`、`CORE_NO_MEDIA`。

### 6.2 Server 侧

1. 新增 `POST /api/v1/index/upsert-clips`，接收 `clip list` 并返回 `indexed/failed`。
2. `POST /api/v1/chat` 保留统一入口，补充 `decision_type/project/patch/reasoning_summary` 的最小响应结构。
3. 错误码建议补齐：`SERVER_VECTOR_UPSERT_FAILED`、`SERVER_CHAT_CONTEXT_INVALID`。

## 7. 客户端代码落点（只规划）

1. `client/src/store/useLaunchpadStore.ts`
   1. 新增统一 action：`startWorkspaceFromLaunchpad`。
   2. 收敛 3 种情况分支到 Store。
2. `client/src/store/useWorkspaceStore.ts`（新建）
   1. 管理 `assets/clips/storyboard/chatTurns/isThinking/mediaProcessing`。
   2. 暴露 `uploadAssets`、`runIngestAndIndex`、`sendChat`。
3. `client/src/services/coreApi.ts`（新建）
   1. 抽离 `projects/import/upload/ingest`。
4. `client/src/services/serverApi.ts`（新建）
   1. 抽离 `chat/indexUpsert`。
5. `client/src/pages/LaunchpadPage.tsx`
   1. 页面只发一个入口 action。
6. `client/src/pages/WorkspacePage.tsx`
   1. 移除本地 `ASSETS/CLIPS/STORYBOARD/CHAT` 常量。
   2. 添加 `Assets Upload` UI 入口并绑定 `workspaceStore`。

## 8. 分阶段实施顺序

1. Phase 1：先落地 `Store State Machine（状态机）` 与统一 action，不改 UI 结构。
2. Phase 2：打通情况 1 + 情况 3（视频链路：`Ingest -> Index`）。
3. Phase 3：打通情况 2（无素材 `chat` 提示策略）。
4. Phase 4：接入 `Workspace Assets Upload`，复用同一视频处理链路。
5. Phase 5：补 `E2E Smoke Test（端到端冒烟测试）` 与错误路径回归。

## 9. 验收标准（DoD）

1. 情况 1：上传视频后自动进入工作台并看到处理中状态，处理完成后素材可见。
2. 情况 2：只输指令可进入工作台并收到“需上传素材”的 AI 引导响应。
3. 情况 3：上传+指令时，必须先完成视频处理再触发 `chat`。
4. 工作台素材区支持上传按钮与拖拽上传，两者都走同一 Store action。
5. 页面层无 `fetch(...)` 与 `window.electron...` 直接调用。

