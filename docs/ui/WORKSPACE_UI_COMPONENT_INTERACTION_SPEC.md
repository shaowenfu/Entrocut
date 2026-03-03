# EntroCut Workspace UI 组件与交互规格（v2, High-Fidelity）

版本：`v2.0`  
设计源：`docs/archive/high-fidelity_prototype.txt`、`docs/archive/high-fidelity_prototype_v2.txt`  
参考规范：`docs/ui/EntroCut_design.md`。

---

## 1. 设计主张（Design Thesis）

1. `AI-first Editing Surface（AI 优先编辑界面）`：对话驱动剪辑决策。
2. `3-Column Composition（三列构图）`：`Media Dock` + `AI Copilot` + `Preview/Storyboard`。
3. `Narrative Storyboard（叙事分镜）`：以只读分镜卡替代传统块状时间线，减少操作噪音。
4. `Decision Transparency（决策透明）`：每次 AI 响应必须带 `reasoning_summary` 与 `ops`。

---

## 2. 页面骨架（Layout）

## 2.1 TopBar

1. 品牌：`EntroCut`
2. 项目标签：`Project_xxx`
3. 操作：`Settings`、`Export`

高度：`56px`

## 2.2 Main Workspace

三列横向分布：

1. 左列 `Media Dock`
2. 中列 `AI Copilot`
3. 右列 `Preview + Storyboard`

列宽规则：

1. 左列可拖拽，范围 `200px - 400px`
2. 中列可拖拽，范围 `300px - 600px`
3. 右列自适应剩余空间

---

## 3. Component Spec（组件规格）

## 3.1 `WorkspaceShell`

职责：

1. 全局布局容器
2. 维护列宽状态
3. 管理拖拽事件监听

状态：

1. `leftWidth`
2. `midWidth`
3. `dragging`

事件：

1. `onResizeStart(side)`
2. `onResizeMove(x)`
3. `onResizeEnd()`

## 3.2 `MediaDock`

职责：

1. 左侧素材入口
2. `Assets` 与 `Clips` 视图切换

输入：

1. `mediaTab: 'assets' | 'clips'`
2. `assets: AssetItem[]`
3. `clips: ClipItem[]`

事件：

1. `onTabChange(tab)`
2. `onAssetClick(assetId)`
3. `onClipClick(clipId)`

## 3.3 `CopilotPane`

职责：

1. 展示会话历史
2. 接受用户指令
3. 显示 `AI Decision Card`

输入：

1. `chatTurns`
2. `isThinking`
3. `promptText`

事件：

1. `onPromptChange(text)`
2. `onSend()`

## 3.4 `DecisionCard`

职责：

1. 展示 `decision_type`
2. 展示 `reasoning_summary`
3. 展示 `ops[]` 操作摘要

字段：

1. `decision_type: UPDATE_PROJECT_CONTRACT | APPLY_PATCH_ONLY | ASK_USER_CLARIFICATION`
2. `reasoning_summary: string`
3. `ops: string[]`

## 3.5 `PreviewStage`

职责：

1. 右侧上半区预览舞台
2. 展示 `Rendering Pipeline` 状态
3. 提供简化 `Scrubber`

状态：

1. `isPreviewBusy`
2. `progress`
3. `timecode`

## 3.6 `StoryboardRail`

职责：

1. 右侧下半区分镜卡列表
2. 只读展示 AI 构建的叙事结构
3. 选中高亮与意图解释

输入：

1. `storyboard: StoryboardScene[]`
2. `activeId`

事件：

1. `onSceneSelect(sceneId)`

---

## 4. Interaction Spec（交互规格）

## 4.1 发送指令（Send Prompt）

1. 用户在 `PromptComposer` 输入文本。
2. 按 `Enter`（不含 `Shift`）或点击 `Send`。
3. 追加 `UserTurn`。
4. `isThinking=true`，输入区禁用。
5. 返回 `AssistantDecision` 后恢复可输入。

## 4.2 AI 决策回显（Decision Feedback）

1. 将 `AssistantDecision` 渲染为 `DecisionCard`。
2. 高亮 `reasoning_summary`。
3. 逐条展示 `ops[]`。

## 4.3 分镜卡替换（Storyboard Replace）

触发：`APPLY_PATCH_ONLY`

1. 保留 `Storyboard` 总长度。
2. 替换被影响 scene 的字段（`title/intention/color`）。
3. 新 scene 自动高亮。

## 4.4 列宽拖拽（Resizable Splitter）

1. `mousedown` 进入拖拽态。
2. `mousemove` 按边界更新列宽。
3. `mouseup` 结束拖拽并解除 `user-select: none`。

## 4.5 素材视图切换（Media Tab Switch）

1. `Assets`：网格缩略卡。
2. `Clips`：语义片段列表（含 `score`）。
3. 切换不清空当前聊天上下文。

---

## 5. 状态与数据契约（State & Data Contract）

## 5.1 ChatTurn

```ts
type ChatTurn =
  | { id: string; role: "user"; content: string }
  | {
      id: string;
      role: "assistant";
      type: "decision";
      decision_type: "UPDATE_PROJECT_CONTRACT" | "APPLY_PATCH_ONLY" | "ASK_USER_CLARIFICATION";
      reasoning_summary: string;
      ops: string[];
    };
```

## 5.2 StoryboardScene

```ts
type StoryboardScene = {
  id: string;
  title: string;
  duration: string;
  intent: string;
  color: string;
  bg: string;
};
```

## 5.3 Media Item

```ts
type AssetItem = { id: string; name: string; duration: string; type: "video" | "audio" };
type ClipItem = {
  id: string;
  parent: string;
  start: string;
  end: string;
  score: string;
  desc: string;
};
```

---

## 6. 视觉规范（Visual Direction）

## 6.1 Token

1. `bgBase`: `#0B0C0E`
2. `bgPanel`: `#141820`
3. `lineSubtle`: `#232936`
4. `accentPrimary`: `#F05A28`
5. `accentSecondary`: `#18C8C1`
6. `textPrimary`: `#F4F6FA`
7. `textMuted`: `#9CA6BD`

## 6.2 字体

1. 标题：`Sora` + `MiSans Heavy`
2. 正文：`IBM Plex Sans` + `MiSans`
3. 时间码：`JetBrains Mono`

## 6.3 动效

1. `thinking`：`Loader spin`
2. `active scene`：`pulse border`
3. `hover`：边框色渐变反馈

---

## 7. 非目标（Non-goals）

1. 不实现复杂 `Timeline Editing`（拖拽编排、Undo/Redo）。
2. 不实现多轨道精细剪辑。
3. 不实现快捷键体系。
4. 不实现 AI 工具链执行细节，仅做决策可视化。

---

## 8. 功能增量建议（Feature Backlog）

1. `Layout`：三列布局与拖拽分栏稳定性。
2. `Copilot`：聊天输入、`DecisionCard` 展示与状态流转。
3. `Storyboard`：高亮、定位、补丁替换反馈。
4. `Health`：顶栏服务状态与会话信息展示。
5. `API Wiring`：接入 `POST /api/v1/chat` 与 `POST /api/v1/render`。
