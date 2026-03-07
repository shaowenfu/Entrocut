# Workspace State Model

本文档定义当前 `prototype mode（原型模式）` 下 `Workspace（工作台）` 的：

1. 主流程
2. 状态切换表
3. `state model（状态模型）`
4. `event -> reducer（事件到状态更新规则）`

目标是让 `Workspace` 的交互和后续 `Core API/WS contract（本地 API/事件契约）` 有稳定边界。

## 1. 核心功能

`Workspace` 当前核心功能如下：

1. 加载并展示项目
2. 展示素材、`clips（片段）`、`storyboard（分镜）`
3. 接收用户 `chat（对话）` 指令
4. 生成或更新 AI 决策结果
5. 导入或补充素材
6. 导出项目
7. 管理与 `Core` 的事件连接
8. 展示错误并允许恢复

## 2. 主流程

当前 `Workspace` 的最小主流程应理解为：

```text
launchpad_enter
-> workspace_loading
-> media_ready / awaiting_media
-> chat_responding
-> ready
-> rendering
-> ready
```

失败分支：

```text
workspace_loading -> failed
media_processing -> failed
chat_responding -> failed
rendering -> failed
```

恢复分支：

```text
failed -> awaiting_media
failed -> media_ready
failed -> ready
```

## 3. 状态模型

## 3.1 数据状态

这些状态表示“当前项目里有什么”。

```ts
interface WorkspaceDataState {
  workspaceId: string | null;
  workspaceName: string | null;
  currentProject: Record<string, unknown> | null;
  assets: WorkspaceAssetItem[];
  clips: WorkspaceClipItem[];
  storyboard: StoryboardScene[];
  chatTurns: ChatTurn[];
  exportResult: ExportResult | null;
  pendingPrompt: string | null;
}
```

## 3.2 业务流程状态

这些状态表示“项目当前进行到哪个业务阶段”。

```ts
type WorkflowState =
  | "prompt_input_required"
  | "awaiting_media"
  | "media_ready"
  | "media_processing"
  | "chat_thinking"
  | "ready"
  | "rendering"
  | "failed";
```

各状态含义：

1. `prompt_input_required`
   刚从启动台进入空项目，等待用户给出明确意图
2. `awaiting_media`
   当前没有素材，不能进入真实剪辑流程
3. `media_ready`
   素材已经可用，但还未形成稳定结果
4. `media_processing`
   正在导入或处理素材
5. `chat_thinking`
   正在处理用户消息，等待 `agent（智能体）` 回复
6. `ready`
   当前结果稳定，可继续 chat、补素材、导出
7. `rendering`
   正在导出
8. `failed`
   最近一个关键业务流程失败

## 3.3 页面加载状态

页面加载和业务流程不应混为一谈。

```ts
type WorkspaceLoadState = "idle" | "loading" | "ready" | "failed";
```

建议以后用这个取代单独的 `isLoadingWorkspace`。

## 3.4 任务状态

当前原型有：

1. `isMediaProcessing`
2. `isThinking`
3. `isExporting`
4. `activeTaskType`
5. `mediaStatusText`

建议统一收敛成：

```ts
type TaskType = "ingest" | "index" | "chat" | "render";
type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

interface ActiveTask {
  id: string;
  type: TaskType;
  status: TaskStatus;
  progress?: number;
  message?: string | null;
}
```

当前阶段可以继续保留 `isMediaProcessing / isThinking / isExporting`，但它们应被视为 `activeTask` 的过渡形态。

## 3.5 对话状态

`chat` 不只是输入框，而是受约束的任务流程。

建议语义：

```ts
type ChatState = "idle" | "responding" | "failed";
```

关键约束：

1. 用户发出一条消息后，必须等待 `agent` 回复完成
2. `chatState === "responding"` 时，不能再次发送下一条消息
3. 素材处理中收到用户消息时，可以选择排队，但不能立即执行

当前原型里这个语义由以下字段共同承担：

1. `isThinking`
2. `workflowState = "chat_thinking"`
3. `activeTaskType = "chat"`
4. `pendingPrompt`

## 3.6 连接状态

连接状态独立于业务流程。

```ts
type EventStreamState = "disconnected" | "connecting" | "connected";
type ReconnectState = "idle" | "reconnecting" | "max_attempts_reached";

interface ConnectionState {
  eventStreamState: EventStreamState;
  reconnectState: ReconnectState;
  lastEventSequence: number;
}
```

即使不直接显示在 UI 中，也必须管理，因为它会影响：

1. 是否能收到进度事件
2. 是否能同步状态更新
3. 是否要触发重连

## 3.7 错误状态

```ts
interface WorkspaceError {
  code: string;
  message: string;
  cause?: string;
  requestId?: string;
}
```

错误分两类理解：

1. 业务错误
   可推动 `workflowState -> failed`
2. 连接错误
   优先体现在 `eventStreamState / reconnectState`

## 4. 派生规则

以下能力不应重复存储，应从状态派生：

```ts
const canSendChat =
  workflowState !== "chat_thinking" &&
  workflowState !== "media_processing" &&
  workflowState !== "rendering" &&
  !isEditLocked;

const canUploadAssets =
  workflowState !== "rendering" &&
  loadState === "ready";

const canExport =
  workflowState === "ready" &&
  eventStreamState === "connected";

const showWorkspaceSpinner =
  loadState === "loading" ||
  workflowState === "media_processing" ||
  workflowState === "chat_thinking";
```

## 5. 状态切换表

## 5.1 加载工作台

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `idle` | 进入工作台 | `loading` | 显示加载态 |
| `loading` | 项目加载成功且有素材 | `ready` 或 `media_ready` | 显示项目数据 |
| `loading` | 项目加载成功但无素材 | `awaiting_media` | 提示先上传素材 |
| `loading` | 加载失败 | `failed` | 显示错误 |

说明：

1. 当前原型里，`initializeWorkspace()` 完成后直接落到 `ready / awaiting_media`
2. 若从 `Launchpad` 带着 `prompt` 进入，还会继续触发 `chat`

## 5.2 从启动台引导进入

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `idle` | `bootstrapFromLaunch` 且有素材 | `media_ready` | 等待后续 chat 或操作 |
| `idle` | `bootstrapFromLaunch` 且无素材 | `prompt_input_required` | 提示补素材或输入意图 |
| `media_ready` | 存在待发送 `prompt` | `chat_thinking` | 自动触发第一轮 chat |
| `prompt_input_required` | 存在待发送 `prompt` | `chat_thinking` | 自动触发第一轮 chat |

## 5.3 导入素材

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `awaiting_media` | 用户上传素材 | `media_processing` | 显示素材处理中 |
| `ready` | 用户补充素材 | `media_processing` | 显示素材处理中 |
| `media_processing` | 导入成功 | `ready` | 刷新素材与片段 |
| `media_processing` | 导入失败 | `failed` | 显示错误 |

补充规则：

1. `media_processing` 期间不能再次发起新的导入
2. 若期间收到用户消息，可排队到 `pendingPrompt`

## 5.4 发送 chat

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `media_ready` | 用户发送消息 | `chat_thinking` | 显示 AI 正在思考 |
| `ready` | 用户发送消息 | `chat_thinking` | 显示 AI 正在思考 |
| `awaiting_media` | 用户发送消息 | 可选：拒绝 / 进入 `chat_thinking` | 取决于产品规则 |
| `media_processing` | 用户发送消息 | 保持 `media_processing` | 记入 `pendingPrompt`，提示排队 |
| `chat_thinking` | AI 返回成功 | `ready` 或 `awaiting_media` | 更新 chat 与 storyboard |
| `chat_thinking` | AI 返回失败 | `failed` | 显示错误 |

关键规则：

1. `chat_thinking` 期间不能继续发送消息
2. `pendingPrompt` 只在素材处理中作为排队缓冲

## 5.5 导出

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `ready` | 用户点击导出 | `rendering` | 锁定编辑并显示导出中 |
| `rendering` | 导出成功 | `ready` | 显示导出结果 |
| `rendering` | 导出失败 | `failed` | 显示错误 |

规则：

1. `rendering` 期间不能再次导出
2. `rendering` 期间不应继续编辑

## 5.6 事件连接

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `disconnected` | 连接开始 | `connecting` | 显示连接中 |
| `connecting` | 连接成功 | `connected` | 显示在线 |
| `connecting` | 连接失败 | `disconnected` 或 `reconnecting` | 显示离线或重连中 |
| `connected` | 连接断开 | `reconnecting` | 显示重连中 |
| `reconnecting` | 重连成功 | `connected` | 恢复在线 |
| `reconnecting` | 超过上限 | `max_attempts_reached` | 显示需要用户处理 |

## 6. 事件定义

```ts
type WorkspaceEvent =
  | { type: "WORKSPACE_LOAD_STARTED"; workspaceId: string; workspaceName?: string }
  | { type: "WORKSPACE_LOAD_SUCCEEDED"; record: PrototypeProjectRecord }
  | { type: "WORKSPACE_LOAD_FAILED"; error: WorkspaceError }
  | { type: "BOOTSTRAP_STARTED"; projectId: string; workspaceName: string; prompt?: string; hasMedia: boolean }
  | { type: "BOOTSTRAP_PROMPT_QUEUED"; prompt: string }
  | { type: "EVENT_STREAM_CONNECT_STARTED" }
  | { type: "EVENT_STREAM_CONNECTED" }
  | { type: "EVENT_STREAM_DISCONNECTED" }
  | { type: "EVENT_STREAM_RECONNECTING" }
  | { type: "EVENT_STREAM_MAX_ATTEMPTS_REACHED" }
  | { type: "ASSET_UPLOAD_STARTED" }
  | { type: "ASSET_UPLOAD_CANCELLED" }
  | { type: "ASSET_UPLOAD_SUCCEEDED"; record: PrototypeProjectRecord }
  | { type: "ASSET_UPLOAD_FAILED"; error: WorkspaceError }
  | { type: "CHAT_STARTED"; prompt: string }
  | { type: "CHAT_QUEUED"; prompt: string }
  | { type: "CHAT_SUCCEEDED"; record: PrototypeProjectRecord; hasMedia: boolean }
  | { type: "CHAT_FAILED"; error: WorkspaceError }
  | { type: "EXPORT_STARTED" }
  | { type: "EXPORT_SUCCEEDED"; result: ExportResult }
  | { type: "EXPORT_FAILED"; error: WorkspaceError }
  | { type: "CLEAR_ERROR" };
```

## 7. Event -> Reducer 规则

## 7.1 工作台加载

1. `WORKSPACE_LOAD_STARTED`
   - `loadState = "loading"`
   - `lastError = null`
2. `WORKSPACE_LOAD_SUCCEEDED`
   - 应用 `record`
   - `loadState = "ready"`
   - `workflowState = record.assets.length > 0 ? "ready" : "awaiting_media"`
3. `WORKSPACE_LOAD_FAILED`
   - `loadState = "failed"`
   - `workflowState = "failed"`
   - `lastError = event.error`

## 7.2 启动台引导

1. `BOOTSTRAP_STARTED`
   - 清空当前展示数据
   - `workspaceId / workspaceName` 赋值
   - `workflowState = hasMedia ? "media_ready" : "prompt_input_required"`
   - `pendingPrompt = prompt ?? null`
2. `BOOTSTRAP_PROMPT_QUEUED`
   - `pendingPrompt = event.prompt`

## 7.3 连接

1. `EVENT_STREAM_CONNECT_STARTED`
   - `eventStreamState = "connecting"`
2. `EVENT_STREAM_CONNECTED`
   - `eventStreamState = "connected"`
   - `reconnectState = "idle"`
3. `EVENT_STREAM_DISCONNECTED`
   - `eventStreamState = "disconnected"`
4. `EVENT_STREAM_RECONNECTING`
   - `reconnectState = "reconnecting"`
5. `EVENT_STREAM_MAX_ATTEMPTS_REACHED`
   - `reconnectState = "max_attempts_reached"`

## 7.4 素材上传

1. `ASSET_UPLOAD_STARTED`
   - `activeTask.type = "ingest"`
   - `workflowState = "media_processing"`
   - `mediaStatusText = "正在刷新 prototype 素材示意..."`
   - `lastError = null`
2. `ASSET_UPLOAD_CANCELLED`
   - 保持现有业务状态
3. `ASSET_UPLOAD_SUCCEEDED`
   - 应用 `record`
   - `workflowState = "ready"`
   - 清空 ingest 任务
4. `ASSET_UPLOAD_FAILED`
   - `workflowState = "failed"`
   - 清空 ingest 任务
   - `lastError = event.error`

## 7.5 Chat

1. `CHAT_STARTED`
   - 在 `chatTurns` 追加用户消息
   - `chatState = "responding"`
   - `workflowState = "chat_thinking"`
   - `activeTask.type = "chat"`
   - `lastError = null`
2. `CHAT_QUEUED`
   - `pendingPrompt = event.prompt`
   - 追加“已排队”提示
3. `CHAT_SUCCEEDED`
   - 应用 `record`
   - `chatState = "idle"`
   - `workflowState = event.hasMedia ? "ready" : "awaiting_media"`
   - 清空 `pendingPrompt`
4. `CHAT_FAILED`
   - `chatState = "failed"`
   - `workflowState = "failed"`
   - 清空 chat 任务
   - `lastError = event.error`

## 7.6 导出

1. `EXPORT_STARTED`
   - `workflowState = "rendering"`
   - `activeTask.type = "render"`
   - `lastError = null`
2. `EXPORT_SUCCEEDED`
   - `workflowState = "ready"`
   - `exportResult = event.result`
   - 清空 render 任务
3. `EXPORT_FAILED`
   - `workflowState = "failed"`
   - 清空 render 任务
   - `lastError = event.error`

## 7.7 通用

1. `CLEAR_ERROR`
   - `lastError = null`

## 8. 当前关键约束

1. `chat_thinking` 期间，不能再发送下一条消息
2. `media_processing` 期间，不能再次发起素材处理
3. `rendering` 期间，不能再次导出
4. `rendering` 期间，应锁定编辑
5. 连接断开不应直接伪装成业务 `ready`
6. `awaiting_media` 下可以允许文本交流，但不能假装具备完整 AI 剪辑能力

## 9. 当前实现与目标模型的差异

当前 [useWorkspaceStore.ts](/home/sherwen/MyProjects/Entrocut/client/src/store/useWorkspaceStore.ts) 已经有状态机雏形，但仍存在 3 个问题：

1. `isLoadingWorkspace / isMediaProcessing / isThinking / isExporting` 与 `workflowState` 并存，语义重复
2. `processingPhase` 和 `activeTaskType` 仍是中间态，尚未统一为一个任务模型
3. 状态更新还分散在多个 `set()` 里，尚未收敛成统一 `reducer`

因此，后续推荐顺序是：

1. 先把 `Workspace` 的 `event -> reducer` 写出来
2. 再把 `useWorkspaceStore.ts` 改成枚举状态 + 统一事件驱动
3. 最后再让页面只消费派生状态
