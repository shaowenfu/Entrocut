# Agent Chat 交互式 UI 组件体系设计方案

日期：`2026-05-05`

## 1. 理念与第一性原理 (First Principles)

不同于传统的纯文本大模型聊天窗口，EntroCut 的核心交互是 **“人机协作剪辑（Chat-to-Cut）”**。在这一理念下，Agent Chat 区域绝不只是一个“文本对话框”，而是 Agent 执行工作的 **“流水线监控面板”**。

基于第一性原理，我们需要满足以下四个核心设计目标：

1.  **打破黑盒 (White-box Execution)**：Agent 的每一步决策（规划、调用工具、观察结果）必须透明。用户需要知道 Agent 为什么这么做，正在做什么。
2.  **渐进式信息揭示 (Progressive Disclosure)**：在侧边栏有限的宽度内，保证极高的信息密度。默认只展示“高信噪比”的状态与最终摘要，将冗长的“思维链（CoT）”和底层工具执行细节折叠，允许用户按需探究。
3.  **富媒体交互 (Interactive Artifacts)**：工具的输出不能是枯燥的 JSON 或文本。例如，`retrieve` 召回的片段（Clips）应该是包含缩略图、时间码的可交互卡片；点击卡片应能联动主界面的视频播放器。
4.  **分层与高扩展性 (Layered Extensibility)**：底层状态与上层渲染必须解耦。系统未来可能会新增音频处理、字幕生成等工具，UI 组件体系必须能够像积木一样即插即用。

---

## 2. Core -> Client 全链路数据与状态流转

要实现丰富的 UI 交互，前提是前后端对 Agent 运行时的状态切片有精确的共识。当前 `core` 已经通过 `agent.step.updated` 事件推送 Agent 的执行轨迹。

### 2.1 后端事件发射 (Core Event Emitting)
在 Agent Loop 运转时，`core/agent_runtime/agent.py` 与 `core/application/store.py` 会产生以下关键事件：
*   `chat.turn.created`: 标志着一个新对话轮次的开始。
*   `agent.step.updated`: 核心状态流转。包含：
    *   `phase`: 如 `planning`, `tool_execution`, `write_back`, `finalizing`。
    *   `reasoning/thought`: 模型返回的思维链（“因为...，所以我决定...”）。
    *   `tool_call`: 即将调用的工具名称与入参。
    *   `observation`: 工具执行完毕后的返回结果（例如：命中 clips 列表，patch 摘要）。
    *   `status`: `running`, `success`, `failed`。

### 2.2 前端状态存储 (Client Store)
在 `client/src/store/useWorkspaceStore.ts` 中，我们需要维护一个结构化的对话树：

```typescript
interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string; // 最终呈现的自然语言回复
  steps: AgentStep[]; // 该轮次内 Agent 执行的所有微步骤
}

interface AgentStep {
  id: string;
  phase: 'planning' | 'tool_calling' | 'observing' | 'finalizing';
  status: 'pending' | 'running' | 'success' | 'error';
  thought?: string; // 思维链
  toolName?: 'retrieve' | 'inspect' | 'patch' | 'preview';
  toolInput?: any;
  toolResult?: any; // 工具执行后的富媒体数据
}
```

---

## 3. UI 组件体系分层架构设计

为了保证视觉统一性和代码可维护性，我们将组件分为三层：**容器层 -> 通用状态层 -> 富媒体定制层**。

### Level 1: 对话轮次容器层 (Turn Container)
*   **组件名**: `<ChatTurnContainer />`
*   **职责**: 区分 User Input 和 Assistant Response。
*   **视觉呈现**:
    *   User: 气泡居右，背景色突出。
    *   Assistant: 紧贴左侧，取消传统气泡，以平铺的方式展示步骤链，使得内容更像是一个“任务执行看板”。

### Level 2: 通用 Agent 步骤指示器 (Step Indicator & CoT)
*   **组件名**: `<AgentStepItem />`
*   **职责**: 渲染单一微步的状态（Loading / Success / Error）以及折叠/展开的思维链。
*   **视觉呈现**:
    *   左侧使用状态 Icon（例如：旋转的 Spinner，绿色的 Check，红色的 Cross），连接着一根垂直的 Timeline 引导线。
    *   **折叠态**: 显示简明摘要，如 `Retrieving clips for "sunset"...`。
    *   **展开态**: 展现大模型的 `Thought`（斜体/次要颜色展示，例如：“用户需要 8 秒的开场，我决定在素材库中检索...”），并提供查看底层 JSON 入参/出参的开发者选项。

### Level 3: 工具专属富媒体组件 (Interactive Tool Artifacts)
根据 `toolName`，动态挂载对应的可视化组件。这些组件不仅展示结果，还负责与 Workspace 的其他区域（如播放器、草案区）通信。

#### 1. 检索召回组件: `<RetrieveArtifact />`
*   **触发场景**: `toolName === 'retrieve'` 且有 `toolResult.matches`。
*   **视觉设计**: 横向或网格排列的微型 Clip 卡片。
    *   **卡片元素**: 视频缩略图（由 source_path 和 start_ms 生成）、相关度评分（Score Badge）、持续时间。
*   **交互联动**:
    *   Hover: 预览动图或在当前卡片内小范围滑动播放。
    *   Click: 触发全局 Action `useWorkspaceStore.getState().playMediaAt(assetId, startMs)`，让中央播放器立刻跳转到该片段。

#### 2. 候选检查组件: `<InspectArtifact />`
*   **触发场景**: `toolName === 'inspect'`。
*   **视觉设计**: 折叠面板（Accordion）。
    *   展示 Agent 检查特定候选片段后的结论（`inspection_summary`）。
    *   以高亮引用的方式展示 Agent 对该片段是否合格的判定（例如：“画面稳定，无抖动，符合要求”）。

#### 3. 草案修改组件: `<PatchArtifact />`
*   **触发场景**: `toolName === 'patch'`。
*   **视觉设计**: Git Diff 风格的操作流展示。
    *   展示简化的操作项：`+ Inserted Shot 1` / `- Removed Shot 2` / `~ Trimmed Shot 3`。
    *   **交互**: 点击可以高亮主界面时间线（Timeline）上对应被修改的轨道块。

#### 4. 渲染预览组件: `<PreviewArtifact />`
*   **触发场景**: `toolName === 'preview'` 且状态为 `success`。
*   **视觉设计**: 一个引人注目的“播放预览”动作块。
    *   显示视频时长、渲染状态。
    *   包含一个主按钮：**"Play Draft Preview"**，点击后将中央播放器的 source 切换为预览输出文件。

---

## 4. 视觉与工程精细化考量

### 4.1 信息密度与空间管理 (Spatial Efficiency)
侧边栏通常宽度在 300px - 400px 之间，空间极其宝贵：
1.  **消除视觉噪音**: 去掉不必要的卡片阴影和边框，使用细线（1px border）、微弱的背景色差（bg-gray-50/bg-gray-100）来区分层级。
2.  **字体排版**:
    *   思维链（Thought）使用 `text-sm`，颜色 `text-gray-500`。
    *   关键操作和工具产物标题使用 `text-sm font-semibold text-gray-900`。
    *   标签（Tags/Badges）采用高反差微型设计（如 `text-[10px]`）。

### 4.2 动画与过渡 (Motion & Transition)
*   **Timeline 流式动画**: 当 Agent 执行下一步时，左侧引导线向下延伸，伴随新组件淡入（Fade In + Slide Down），给用户“机器正在思考和行动”的心智模型。
*   **折叠过渡**: 使用 `framer-motion` 或 CSS `grid-template-rows: 1fr` 技巧实现平滑的折叠/展开动画，防止生硬的跳变。

### 4.3 错误隔离 (Graceful Degradation)
当某个工具执行失败时（如 `inspect` 超时）：
*   Timeline 该步骤节点变为红色错误状态。
*   展开面板内展示对用户友好的报错说明（非枯燥的 Stack Trace），并提供 `[Retry]` 或 `[Skip]` 的快捷操作选项，不阻塞整个对话流。

---

## 5. 实施路径与推荐 PR 切分

为了平稳落地这一套复杂的组件体系，建议按以下 3 个 PR 逐步推进：

### PR 1: 核心基础结构与数据接线 (Infrastructure & Wiring)
*   **目标**: 建立状态模型，跑通基础 Timeline。
*   **改动**:
    1.  更新 `useWorkspaceStore.ts` 引入 `ChatTurn` 和 `AgentStep` 状态树。
    2.  在 `coreClient.ts` 中拦截 `agent.step.updated` 并映射到 Store 中。
    3.  实现基础组件 `<AgentTimeline />` 和 `<AgentStepItem />`，只渲染纯文本的 `Thought` 和折叠面板，跑通 Loading 和 Success 状态。

### PR 2: 核心富媒体工具组件 (Rich Media Artifacts)
*   **目标**: 实现检索和检查的可视化卡片。
*   **改动**:
    1.  新增 `<RetrieveArtifact />` 组件，消费 `toolResult` 渲染 Clip 缩略图卡片。
    2.  新增 `<InspectArtifact />` 组件，展示片段评价。
    3.  建立 UI 与中央播放器的事件总线或状态联动（点击卡片 -> 触发播放）。

### PR 3: Patch/Preview 交互与视觉打磨 (Polishing & Workspace Sync)
*   **目标**: 完成草案变更的可视化，以及所有视觉动画的精细化调整。
*   **改动**:
    1.  新增 `<PatchArtifact />` 展示操作 Diff。
    2.  新增 `<PreviewArtifact />` 组件，提供一键播放入口。
    3.  全面优化 CSS（Tailwind），引入平滑过渡动画，确保在深色/浅色模式下的信息对比度最优。

---
> 架构设计基于 EntroCut “对话即剪辑”第一性原理。我们不是在做一个好看的聊天框，我们是在为一个具备物理行动能力的 Agent 设计“透明的控制台”。
