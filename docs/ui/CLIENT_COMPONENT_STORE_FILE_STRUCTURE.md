# Client 组件与状态文件结构（Launchpad + Workspace）

本文档描述当前 `client` 的落地结构与下一步拆分方向。  
目标：先保证页面级稳定，再按功能切片逐步模块化。

## 1. 当前结构（已落地）

```text
client/src
├── App.tsx
├── index.css
├── main.tsx
├── mocks
│   └── launchpad.ts
├── pages
│   ├── LaunchpadPage.tsx
│   └── WorkspacePage.tsx
├── services
│   └── health.ts
└── utils
    └── session.ts
```

## 2. 文件职责

1. `App.tsx`
   1. 页面壳层。
   2. 管理 `launchpad/workspace` 视图切换。
2. `pages/LaunchpadPage.tsx`
   1. 启动台 UI。
   2. 混合输入区（拖拽 + Prompt）。
   3. 最近项目卡片列表。
3. `pages/WorkspacePage.tsx`
   1. 三栏工作台 UI。
   2. `Copilot + Preview + Storyboard` 交互。
   3. 顶栏 `Health` 与导出锁状态。
4. `mocks/launchpad.ts`
   1. 启动台 mock 数据集中定义。
   2. 明确 `TODO(contract/api)` 替换位。
5. `services/health.ts`
   1. `core/server` 健康探测。
6. `utils/session.ts`
   1. 基于 `project_id` 的 `session_id` 生成与缓存。

## 3. 状态切分（当前形态）

### 3.1 App-level State

1. `view: "launchpad" | "workspace"`
2. `activeWorkspaceName: string`

### 3.2 LaunchpadPage State

1. `prompt: string`
2. `isDropHovering: boolean`
3. `hintIndex: number`

### 3.3 WorkspacePage State

1. `chatTurns`
2. `isThinking`
3. `storyboard`
4. `layout widths`
5. `isExporting / isEditLocked`
6. `serviceHealth`
7. `playback state`

## 4. 下一步目标结构（按功能演进）

```text
client/src
├── components
│   ├── launchpad
│   │   ├── IntentDropZone.tsx
│   │   ├── RecentWorkspaceGrid.tsx
│   │   └── RecentWorkspaceCard.tsx
│   └── workspace
│       ├── TopBar.tsx
│       ├── MediaDock.tsx
│       ├── CopilotPane.tsx
│       ├── PreviewStage.tsx
│       └── StoryboardRail.tsx
├── store
│   ├── app-store.ts
│   ├── launchpad-store.ts
│   └── workspace-store.ts
└── services
    ├── project-service.ts
    ├── chat-service.ts
    └── render-service.ts
```

## 5. 接线顺序（严格）

1. `Launchpad` 先接 `Project Summary API`（替换 `mocks/launchpad.ts`）。
2. `Workspace` 再接 `chat/render`，替换本地模拟流转。
3. 每次替换只动一个功能切片，确保可回归测试。
