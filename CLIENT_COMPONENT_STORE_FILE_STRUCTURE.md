# Client UI 文件结构（基于新版 High-Fidelity Prototype）

本文档定义 `client` 第一阶段 UI 重构后的目标结构。核心变化：从“左 AI + 右工作台”切到 `3-Column Workspace（三列工作台）`，并将底部交互改为 `AI Storyboard（AI 分镜卡片）`。

## 1. 目标目录树（Target Tree）

```text
client/src
├── App.tsx
├── main.tsx
├── index.css
├── styles
│   └── workspace.css
├── components
│   ├── topbar
│   │   └── TopBar.tsx
│   ├── workspace
│   │   ├── WorkspaceLayout.tsx
│   │   ├── ResizeHandle.tsx
│   │   └── WorkspaceShell.tsx
│   ├── media-dock
│   │   ├── MediaDock.tsx
│   │   ├── MediaTabSwitch.tsx
│   │   ├── AssetGrid.tsx
│   │   └── ClipList.tsx
│   ├── copilot
│   │   ├── CopilotPane.tsx
│   │   ├── ChatThread.tsx
│   │   ├── DecisionCard.tsx
│   │   └── PromptComposer.tsx
│   └── stage
│       ├── PreviewStage.tsx
│       ├── ScrubberBar.tsx
│       ├── StoryboardRail.tsx
│       └── StoryboardCard.tsx
├── store
│   ├── types.ts
│   ├── actions.ts
│   ├── reducer.ts
│   ├── selectors.ts
│   ├── initial-state.ts
│   └── workspace-context.tsx
└── services
    ├── api-client.ts
    ├── chat-service.ts
    └── render-service.ts
```

## 2. 组件职责映射（Component Mapping）

1. `TopBar`
   1. 品牌、项目名、`Settings（设置）`、`Export（导出）`。
2. `MediaDock`
   1. 左列素材入口，`Assets/Clips` 双视图。
3. `CopilotPane`
   1. 中列 `AI Copilot` 对话与 `DecisionCard` 决策解释。
4. `PreviewStage`
   1. 右列上半部分播放器舞台与 `Scrubber（进度条）`。
5. `StoryboardRail`
   1. 右列下半部分只读分镜卡，替代旧 `Timeline（时间线）`。
6. `ResizeHandle`
   1. 左右两条可拖拽分栏线，控制列宽。

## 3. Store 结构（State Store）

### 3.1 `UiLayoutState`

1. `leftWidth: number`
2. `midWidth: number`
3. `dragging: 'left' | 'mid' | null`
4. `mediaTab: 'assets' | 'clips'`

### 3.2 `CopilotState`

1. `chatTurns: ChatTurn[]`
2. `promptText: string`
3. `isThinking: boolean`

### 3.3 `StageState`

1. `highlightStoryboardId: string | null`
2. `isPreviewBusy: boolean`
3. `playbackProgress: number`

### 3.4 `DomainDataState`

1. `assets: AssetItem[]`
2. `clips: ClipItem[]`
3. `storyboard: StoryboardScene[]`

## 4. Action 设计（Action Contract）

1. `layout/resize_started`
2. `layout/resize_updated`
3. `layout/resize_ended`
4. `media/tab_changed`
5. `copilot/prompt_changed`
6. `chat/request_started`
7. `chat/response_received`
8. `storyboard/scene_highlighted`
9. `storyboard/scene_replaced`
10. `render/request_started`
11. `render/request_finished`

## 5. 第一阶段可交付范围（Phase-1 Deliverable）

1. 三列布局与拖拽分栏可用。
2. `Assets/Clips` 视图切换可用。
3. `Copilot` 对话区可输入与显示决策卡。
4. 右侧预览舞台 + 底部分镜卡可交互高亮。
5. 暂时允许使用 `Mock Flow（模拟流程）` 替代真实 API。

## 6. 第二阶段接线位（Phase-2 Wiring）

1. `chat-service.ts` 接 `POST /api/v1/chat`。
2. `render-service.ts` 接 `POST /api/v1/render`。
3. 将 `DecisionCard.ops` 与 `StoryboardRail` 的 replace 动作绑定。
