# EntroCut UI 组件与交互规格（Launchpad + Workspace, MVP）

版本：`v3.0`  
设计源：`launchboard_prototype.txt` + `Workspace V4`  
对应实现：`client/src/App.tsx`、`client/src/pages/LaunchpadPage.tsx`、`client/src/pages/WorkspacePage.tsx`

## 1. 页面层级（Page Composition）

1. `AppShell`
   1. `LaunchpadPage`
   2. `WorkspacePage`
2. 默认入口：`LaunchpadPage`
3. 导航方式：本地状态切换（MVP 阶段不引入 `router`）

## 2. Launchpad Component Spec

### 2.1 `LaunchpadPage`

职责：

1. 渲染启动台全布局。
2. 承担“新建项目”与“打开最近项目”的交互入口。
3. 向 `AppShell` 发送 `onOpenWorkspace(workspaceName)`。

输入：

1. `onOpenWorkspace(workspaceName: string)`

内部状态：

1. `prompt: string`
2. `isDropHovering: boolean`
3. `hintIndex: number`

### 2.2 `IntentDropZone`

职责：

1. 接受拖拽素材目录（当前仅 UI mock）。
2. 提供 Prompt 输入框与创建按钮。

事件：

1. `onDragOver/onDragLeave/onDrop`
2. `onPromptChange`
3. `onCreateFromPrompt`

### 2.3 `RecentWorkspaceGrid`

职责：

1. 展示项目卡片与 AI 状态信息。
2. 点击卡片直接进入对应 Workspace。

卡片字段：

1. `title`
2. `lastActiveText`
3. `aiStatus`
4. `lastAiEdit`
5. `storageType`

## 3. Workspace Component Spec

### 3.1 `WorkspacePage`

职责：

1. 承载三栏布局与全局状态（导出锁、连接健康、播放状态）。
2. 接收 `workspaceName` 并展示在顶栏。
3. 提供返回 Launchpad 的入口。

输入：

1. `workspaceName: string`
2. `onBackLaunchpad?: () => void`

### 3.2 `TopBar`

职责：

1. 项目上下文展示。
2. `core/server health` 展示。
3. 导出按钮与 `Edit Lock` 状态提示。

### 3.3 `Media Dock`

职责：

1. `Assets/Clips` 双视图切换。
2. 展示素材与切片（当前 mock）。

### 3.4 `Copilot Pane`

职责：

1. 展示 `ChatTurn`。
2. 渲染 `DecisionCard`（`reasoning_summary + ops`）。
3. 接收 Prompt 并触发发送逻辑。

### 3.5 `Stage + Storyboard`

职责：

1. 预览渲染状态反馈。
2. `Scrubber` 与时间显示。
3. 分镜卡片定位与 patch 高亮。

## 4. Interaction Spec（关键交互）

### 4.1 启动项目（Launch）

1. 用户在 Launchpad 拖入目录或输入 Prompt。
2. 当前行为仅触发本地页面跳转到 Workspace（mock）。
3. 后续替换为 `Create Project API` + `Ingest Trigger`。

### 4.2 快速回到项目（Re-entry）

1. 用户点击最近项目卡片。
2. `AppShell` 设置 `activeWorkspaceName`。
3. 页面切换到 `WorkspacePage`。

### 4.3 AI 编辑回显（Workspace）

1. 用户发送 Prompt。
2. 进入 `isThinking`。
3. 返回 `AssistantDecision` 后：
   1. 渲染 `DecisionCard`
   2. 更新分镜
   3. 触发 patch 高亮

### 4.4 导出锁（Edit Lock）

1. 点击 `Export` 后置 `isEditLocked=true`。
2. 聊天输入、切换等编辑行为禁用。
3. 导出结束后自动解除锁定。

## 5. Mock 边界与替换位（必须保留）

1. `client/src/mocks/launchpad.ts`
   1. `MOCK_LAUNCHPAD_PROJECTS`
   2. `MOCK_LAUNCHPAD_HINTS`
2. `client/src/pages/LaunchpadPage.tsx`
   1. `TODO(api): POST /api/v1/projects`
   2. `TODO(api): POST /api/v1/projects/import`
3. `client/src/pages/WorkspacePage.tsx`
   1. 聊天与分镜仍为本地模拟流转（待接 `POST /api/v1/chat`、`POST /api/v1/render`）

## 6. 非目标（MVP）

1. 不做多页面路由系统与深链接。
2. 不做 Launchpad 的真实文件系统扫描。
3. 不做复杂项目过滤、排序、批量操作。
4. 不做复杂 Timeline 操作（Undo/快捷键/关键帧）。
