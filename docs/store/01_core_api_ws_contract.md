# Core API/WS Contract

本文档定义当前 `Client -> Core` 的真实本地契约，目标是让前端、`core`、测试和文档对同一套状态模型达成一致。

当前版本的核心结论只有一条：

`公开契约已经不再暴露单一 workflow_state，而是改成 summary_state + media_summary + runtime_state + capabilities + active_tasks。`

`SQLite` 中仍保留 `workflow_state` 列，但它只用于内部兼容持久化，不属于公开 `API/WS contract（接口/事件契约）`。

## 1. 设计目标

当前 `core` 只对前端提供以下能力：

1. 创建和查询项目
2. 导入素材
3. 发送 `chat` 指令并驱动最小 `planner-driven loop（规划驱动循环）`
4. 导出 `EditDraft`
5. 通过 `WebSocket event stream（事件流）` 推送状态变化

当前明确 `Non-goals（非目标）`：

1. 不暴露底层 `LLM / Embedding / FFmpeg` 实现细节
2. 不用一个总状态字段替代真实业务事实
3. 不把 `WebSocket` 当命令入口

## 2. 顶层原则

### 2.1 状态分层

前端应把状态理解为五层事实：

1. `project`
   - 项目元数据
2. `summary_state`
   - 项目级摘要状态
3. `media_summary`
   - 素材处理聚合状态
4. `runtime_state`
   - `agent runtime（智能体运行时）` 事实
5. `capabilities`
   - 动作准入开关

### 2.2 任务分层

异步过程不再依赖单一项目状态驱动，而是通过 `Task.slot` 表达资源占用范围：

1. `media`
2. `agent`
3. `export`

`active_tasks` 是权威任务集合。  
`active_task` 仅为兼容旧调用方保留的便利字段。

### 2.3 空项目合法

`POST /api/v1/projects` 允许创建空项目。  
空项目可以进入 `planning_only` 的 `chat mode（聊天模式）`，但不能执行依赖素材索引的工具。

## 3. 顶层资源模型

### 3.1 Project

```ts
type ProjectSummaryState =
  | "blank"
  | "planning"
  | "media_processing"
  | "editing"
  | "exporting"
  | "attention_required";

type ProjectLifecycleState = "active" | "archived";

interface Project {
  id: string;
  title: string;
  summary_state?: ProjectSummaryState | null;
  lifecycle_state?: ProjectLifecycleState;
  created_at: string;
  updated_at: string;
}
```

说明：

1. `Project` 只保留项目元信息
2. `summary_state` 是公开摘要状态
3. 公开模型中不再包含 `workflow_state`

### 3.2 Asset

```ts
type AssetType = "video" | "audio";
type AssetProcessingStage = "pending" | "segmenting" | "vectorizing" | "ready" | "failed";

interface Asset {
  id: string;
  name: string;
  duration_ms: number;
  type: AssetType;
  source_path?: string | null;
  processing_stage?: AssetProcessingStage;
  processing_progress?: number | null;
  clip_count?: number;
  indexed_clip_count?: number;
  last_error?: Record<string, unknown> | null;
  updated_at?: string | null;
}
```

### 3.3 Clip / Shot / Scene / EditDraft

```ts
interface Clip {
  id: string;
  asset_id: string;
  source_start_ms: number;
  source_end_ms: number;
  visual_desc: string;
  semantic_tags: string[];
  confidence?: number | null;
  thumbnail_ref?: string | null;
}

interface Shot {
  id: string;
  clip_id: string;
  source_in_ms: number;
  source_out_ms: number;
  order: number;
  enabled: boolean;
  label?: string | null;
  intent?: string | null;
  note?: string | null;
  locked_fields?: Array<"source_range" | "order" | "clip_id" | "enabled">;
}

interface Scene {
  id: string;
  shot_ids: string[];
  order: number;
  enabled: boolean;
  label?: string | null;
  intent?: string | null;
  note?: string | null;
  locked_fields?: Array<"shot_ids" | "order" | "enabled" | "intent">;
}

interface EditDraft {
  id: string;
  project_id: string;
  version: number;
  status: "draft" | "ready" | "rendering" | "failed";
  assets: Asset[];
  clips: Clip[];
  shots: Shot[];
  scenes?: Scene[] | null;
  selected_scene_id?: string | null;
  selected_shot_id?: string | null;
  created_at: string;
  updated_at: string;
}
```

### 3.4 ChatTurn

```ts
type ChatTurn =
  | {
      id: string;
      role: "user";
      content: string;
    }
  | {
      id: string;
      role: "assistant";
      type: "decision";
      decision_type: "EDIT_DRAFT_PATCH";
      reasoning_summary: string;
      ops: Array<{
        id: string;
        action: string;
        target: string;
        summary: string;
      }>;
    };
```

### 3.5 Task

```ts
type TaskSlot = "media" | "agent" | "export";
type TaskType = "ingest" | "index" | "chat" | "render";
type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

interface Task {
  id: string;
  slot?: TaskSlot;
  type: TaskType;
  status: TaskStatus;
  owner_type?: "project" | "asset" | "draft";
  owner_id?: string | null;
  progress: number | null;
  message: string | null;
  result?: Record<string, unknown>;
  error?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}
```

### 3.6 ProjectMediaSummary

```ts
interface ProjectMediaSummary {
  asset_count: number;
  pending_asset_count: number;
  processing_asset_count: number;
  ready_asset_count: number;
  failed_asset_count: number;
  total_clip_count: number;
  indexed_clip_count: number;
  retrieval_ready: boolean;
}
```

### 3.7 ProjectRuntimeState

```ts
type ChatMode = "planning_only" | "editing";
type ConversationFeedbackState = "unknown" | "clarify" | "approve" | "reject" | "revise";
type ExecutionAgentRunState = "idle" | "planning" | "executing_tool" | "waiting_user" | "failed";

interface ProjectRuntimeState {
  goal_state: {
    brief?: string | null;
    constraints: string[];
    preferences: string[];
    open_questions: string[];
    updated_at?: string | null;
  };
  focus_state: {
    scope_type: "project" | "scene" | "shot";
    scene_id?: string | null;
    shot_id?: string | null;
    updated_at?: string | null;
  };
  conversation_state: {
    pending_questions: string[];
    confirmed_facts: string[];
    latest_user_feedback: ConversationFeedbackState;
    updated_at?: string | null;
  };
  retrieval_state: {
    last_query?: string | null;
    candidate_clip_ids: string[];
    retrieval_ready: boolean;
    blocking_reason?: string | null;
    updated_at?: string | null;
  };
  execution_state: {
    agent_run_state: ExecutionAgentRunState;
    current_task_id?: string | null;
    last_tool_name?: string | null;
    last_error?: Record<string, unknown> | null;
    updated_at?: string | null;
  };
  updated_at?: string | null;
}
```

### 3.8 ProjectCapabilities

```ts
interface ProjectCapabilities {
  can_send_chat: boolean;
  chat_mode: ChatMode;
  can_retrieve: boolean;
  can_inspect: boolean;
  can_patch_draft: boolean;
  can_preview: boolean;
  can_export: boolean;
  blocking_reasons: string[];
}
```

### 3.9 WorkspaceSnapshot

```ts
interface WorkspaceSnapshot {
  project: Project;
  edit_draft: EditDraft;
  chat_turns: ChatTurn[];
  summary_state?: ProjectSummaryState | null;
  media_summary: ProjectMediaSummary;
  runtime_state: ProjectRuntimeState;
  capabilities: ProjectCapabilities;
  active_tasks: Task[];
  active_task: Task | null;
}
```

说明：

1. `edit_draft` 是剪辑事实源
2. `summary_state` 是项目级摘要状态
3. `runtime_state` 是 `agent` 决策事实源
4. `capabilities` 是前端和 `agent` 的准入依据
5. `active_tasks` 是异步过程事实源

## 4. 通用 Envelope

### 4.1 HTTP ErrorEnvelope

```ts
interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}
```

规则：

1. `code` 供前端分支处理
2. `message` 供用户展示
3. `details` 只携带必要上下文
4. 不暴露内部栈信息

### 4.2 WebSocket EventEnvelope

```ts
interface EventEnvelope<T = unknown> {
  sequence: number;
  event: string;
  project_id: string;
  emitted_at: string;
  data: T;
}
```

## 5. HTTP API Contract

接口前缀统一为：

```text
/api/v1
```

### 5.1 `GET /health`

用途：

1. 检查服务是否存活
2. 返回运行阶段与模式

示例：

```json
{
  "status": "ok",
  "service": "core",
  "version": "0.7.0",
  "phase": "clean_room_rewrite",
  "mode": "prototype_backed",
  "timestamp": "2026-03-31T10:00:00Z",
  "notes": [
    "Legacy business logic has been removed.",
    "This service now bootstraps local SQLite persistence and per-project workspaces."
  ]
}
```

### 5.2 `GET /api/v1/runtime/capabilities`

用途：

1. 前端探测 `core` 暴露的表面能力
2. 原型期做 `feature gating（能力开关）`

### 5.3 `GET /api/v1/projects`

用途：

1. 启动台加载项目列表

查询参数：

1. `limit`
   - 可选
   - 默认 `20`
   - 取值范围 `1..100`

响应示例：

```json
{
  "projects": [
    {
      "id": "proj_001",
      "title": "Japan Ski Trip",
      "summary_state": "editing",
      "lifecycle_state": "active",
      "created_at": "2026-03-07T09:00:00Z",
      "updated_at": "2026-03-07T09:05:00Z"
    }
  ]
}
```

### 5.4 `POST /api/v1/projects`

用途：

1. 创建空项目
2. 创建带 `prompt` 的项目
3. 创建带 `media reference（素材引用）` 的项目
4. 创建带 `prompt + media` 的项目

请求：

```ts
interface CreateProjectRequest {
  title?: string;
  prompt?: string;
  media?: {
    folder_path?: string;
    files?: Array<{
      name: string;
      path?: string;
      size_bytes?: number | null;
      mime_type?: string | null;
    }>;
  };
}
```

规则：

1. 空请求合法
2. `media` 传的是引用，不是二进制上传
3. 若没有任何输入，项目会以 `blank + planning_only` 起步

响应：

```json
{
  "project": {
    "id": "proj_001",
    "title": "Untitled Project",
    "summary_state": "blank",
    "lifecycle_state": "active",
    "created_at": "2026-03-31T10:00:00Z",
    "updated_at": "2026-03-31T10:00:00Z"
  },
  "workspace": {
    "project": {
      "id": "proj_001",
      "title": "Untitled Project",
      "summary_state": "blank",
      "lifecycle_state": "active",
      "created_at": "2026-03-31T10:00:00Z",
      "updated_at": "2026-03-31T10:00:00Z"
    },
    "edit_draft": {
      "id": "draft_001",
      "project_id": "proj_001",
      "version": 1,
      "status": "draft",
      "assets": [],
      "clips": [],
      "shots": [],
      "scenes": null,
      "selected_scene_id": null,
      "selected_shot_id": null,
      "created_at": "2026-03-31T10:00:00Z",
      "updated_at": "2026-03-31T10:00:00Z"
    },
    "chat_turns": [],
    "summary_state": "blank",
    "media_summary": {
      "asset_count": 0,
      "pending_asset_count": 0,
      "processing_asset_count": 0,
      "ready_asset_count": 0,
      "failed_asset_count": 0,
      "total_clip_count": 0,
      "indexed_clip_count": 0,
      "retrieval_ready": false
    },
    "runtime_state": {
      "goal_state": {
        "brief": null,
        "constraints": [],
        "preferences": [],
        "open_questions": [],
        "updated_at": "2026-03-31T10:00:00Z"
      },
      "focus_state": {
        "scope_type": "project",
        "scene_id": null,
        "shot_id": null,
        "updated_at": "2026-03-31T10:00:00Z"
      },
      "conversation_state": {
        "pending_questions": [],
        "confirmed_facts": [],
        "latest_user_feedback": "unknown",
        "updated_at": "2026-03-31T10:00:00Z"
      },
      "retrieval_state": {
        "last_query": null,
        "candidate_clip_ids": [],
        "retrieval_ready": false,
        "blocking_reason": "media_index_not_ready",
        "updated_at": "2026-03-31T10:00:00Z"
      },
      "execution_state": {
        "agent_run_state": "idle",
        "current_task_id": null,
        "last_tool_name": null,
        "last_error": null,
        "updated_at": "2026-03-31T10:00:00Z"
      },
      "updated_at": "2026-03-31T10:00:00Z"
    },
    "capabilities": {
      "can_send_chat": true,
      "chat_mode": "planning_only",
      "can_retrieve": false,
      "can_inspect": false,
      "can_patch_draft": false,
      "can_preview": false,
      "can_export": false,
      "blocking_reasons": ["media_index_not_ready"]
    },
    "active_tasks": [],
    "active_task": null
  }
}
```

### 5.5 `GET /api/v1/projects/{project_id}`

用途：

1. 工作台初始化读取
2. 获取完整 `WorkspaceSnapshot`

响应：

```json
{
  "workspace": {
    "project": {
      "id": "proj_001",
      "title": "Japan Ski Trip",
      "summary_state": "editing",
      "lifecycle_state": "active",
      "created_at": "2026-03-07T09:00:00Z",
      "updated_at": "2026-03-07T09:10:00Z"
    },
    "edit_draft": {
      "id": "draft_001",
      "project_id": "proj_001",
      "version": 3,
      "status": "ready",
      "assets": [],
      "clips": [],
      "shots": [],
      "scenes": null,
      "selected_scene_id": null,
      "selected_shot_id": null,
      "created_at": "2026-03-07T09:00:00Z",
      "updated_at": "2026-03-07T09:10:00Z"
    },
    "chat_turns": [],
    "summary_state": "editing",
    "media_summary": {
      "asset_count": 2,
      "pending_asset_count": 0,
      "processing_asset_count": 0,
      "ready_asset_count": 2,
      "failed_asset_count": 0,
      "total_clip_count": 4,
      "indexed_clip_count": 4,
      "retrieval_ready": true
    },
    "runtime_state": {
      "goal_state": {
        "brief": "做一个旅行开头",
        "constraints": [],
        "preferences": [],
        "open_questions": [],
        "updated_at": "2026-03-07T09:10:00Z"
      },
      "focus_state": {
        "scope_type": "project",
        "scene_id": null,
        "shot_id": null,
        "updated_at": "2026-03-07T09:10:00Z"
      },
      "conversation_state": {
        "pending_questions": [],
        "confirmed_facts": [],
        "latest_user_feedback": "unknown",
        "updated_at": "2026-03-07T09:10:00Z"
      },
      "retrieval_state": {
        "last_query": null,
        "candidate_clip_ids": [],
        "retrieval_ready": true,
        "blocking_reason": null,
        "updated_at": "2026-03-07T09:10:00Z"
      },
      "execution_state": {
        "agent_run_state": "idle",
        "current_task_id": null,
        "last_tool_name": null,
        "last_error": null,
        "updated_at": "2026-03-07T09:10:00Z"
      },
      "updated_at": "2026-03-07T09:10:00Z"
    },
    "capabilities": {
      "can_send_chat": true,
      "chat_mode": "editing",
      "can_retrieve": true,
      "can_inspect": true,
      "can_patch_draft": true,
      "can_preview": false,
      "can_export": true,
      "blocking_reasons": []
    },
    "active_tasks": [],
    "active_task": null
  }
}
```

### 5.6 `POST /api/v1/projects/{project_id}/assets:import`

用途：

1. 导入或补充素材

请求：

```ts
interface ImportAssetsRequest {
  media: {
    folder_path?: string;
    files?: Array<{
      name: string;
      path?: string;
      size_bytes?: number | null;
      mime_type?: string | null;
    }>;
  };
}
```

响应：

```json
{
  "task": {
    "id": "task_ingest_001",
    "slot": "media",
    "type": "ingest",
    "status": "queued",
    "owner_type": "project",
    "owner_id": "proj_001",
    "progress": 0,
    "message": "Media ingest queued",
    "result": {},
    "error": null,
    "created_at": "2026-03-31T10:01:00Z",
    "updated_at": "2026-03-31T10:01:00Z"
  }
}
```

### 5.7 `POST /api/v1/projects/{project_id}/chat`

用途：

1. 发送用户 `chat` 指令

请求：

```ts
interface ChatRequest {
  prompt: string;
  model?: string;
  target?: {
    scene_id?: string | null;
    shot_id?: string | null;
  };
}
```

请求头：

1. `X-Routing-Mode`
   - `Platform` 或 `BYOK`
2. `X-BYOK-Key`
   - 当 `X-Routing-Mode = BYOK` 时使用
3. `X-BYOK-BaseURL`
   - 可选，自定义 `BYOK` 上游地址

规则：

1. `Platform` 模式要求已同步本地 `auth session`
2. 空项目允许发起 `chat`
3. `planning_only` 只禁止依赖素材索引的工具，不禁止需求澄清

响应：

```json
{
  "task": {
    "id": "task_chat_001",
    "slot": "agent",
    "type": "chat",
    "status": "queued",
    "owner_type": "project",
    "owner_id": "proj_001",
    "progress": null,
    "message": "Chat queued",
    "result": {},
    "error": null,
    "created_at": "2026-03-31T10:02:00Z",
    "updated_at": "2026-03-31T10:02:00Z"
  }
}
```

### 5.8 `POST /api/v1/projects/{project_id}/export`

用途：

1. 导出当前 `EditDraft`

请求：

```ts
interface ExportRequest {
  format?: string;
  quality?: string;
}
```

规则：

1. 至少需要一个 `shot`
2. `agent` 或 `export` 任务运行时会拒绝新的导出

## 6. WebSocket Event Contract

连接地址：

```text
GET /api/v1/projects/{project_id}/events
```

`WebSocket` 只负责项目级状态推进，不承担命令入口。

### 6.1 `workspace.snapshot`

用途：

1. 连接建立后推送完整快照
2. 重连后做状态重同步

载荷：

```ts
interface WorkspaceSnapshotEventData {
  workspace: WorkspaceSnapshot;
}
```

### 6.2 `task.updated`

用途：

1. 推送任务状态变化
2. 更新 `active_tasks`

载荷：

```ts
interface TaskUpdatedEventData {
  task: Task;
}
```

说明：

1. 不再附带 `workflow_state`
2. 前端应基于 `task.slot + task.status` 推导局部加载态

### 6.3 `chat.turn.created`

```ts
interface ChatTurnCreatedEventData {
  turn: ChatTurn;
}
```

### 6.4 `edit_draft.updated`

```ts
interface EditDraftUpdatedEventData {
  edit_draft: EditDraft;
}
```

### 6.5 `asset.updated`

用途：

1. 推送发生变化的素材子集

```ts
interface AssetUpdatedEventData {
  assets: Asset[];
}
```

### 6.6 `project.updated`

用途：

1. 推送项目元数据变化

```ts
interface ProjectUpdatedEventData {
  project: Project;
}
```

### 6.7 `project.summary.updated`

用途：

1. 推送项目摘要状态变化

```ts
interface ProjectSummaryUpdatedEventData {
  summary_state: ProjectSummaryState;
}
```

### 6.8 `capabilities.updated`

用途：

1. 推送动作准入变化

```ts
interface CapabilitiesUpdatedEventData {
  capabilities: ProjectCapabilities;
}
```

### 6.9 `export.completed`

```ts
interface ExportCompletedEventData {
  result: {
    render_type: "export";
    output_url: string;
    duration_ms: number;
    file_size_bytes: number | null;
    thumbnail_url: string | null;
    format: string;
    quality: string | null;
    resolution: string | null;
  };
}
```

### 6.10 `error.occurred`

用途：

1. 推送流程级错误

```ts
interface ErrorOccurredEventData {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
```

说明：

1. 当前 `WS` 错误事件不再携带 `workflow_state`
2. 当前 `WS` 错误事件也不保证携带 `request_id`
3. 错误后的项目摘要状态通常会转入 `attention_required`

### 6.11 `agent.step.updated`

用途：

1. 推送 `agent loop` 的阶段性进度
2. 便于调试和未来的细粒度 UI

```ts
interface AgentStepUpdatedEventData {
  phase: string;
  summary: string;
  details: Record<string, unknown>;
}
```

## 7. HTTP 与 WS 的职责分工

### HTTP 负责

1. 创建项目
2. 读取快照
3. 发起导入
4. 发起 `chat`
5. 发起导出

### WS 负责

1. 推送任务状态
2. 推送草案变化
3. 推送素材变化
4. 推送项目摘要状态
5. 推送 `capabilities`
6. 推送导出结果
7. 推送流程级错误

## 8. 错误语义

当前高频错误码包括：

### 通用

1. `PROJECT_NOT_FOUND`
2. `TASK_ALREADY_RUNNING`
3. `CORE_UNHANDLED`

### 素材导入

1. `MEDIA_REFERENCE_REQUIRED`
2. `MEDIA_IMPORT_FAILED`

### Chat

1. `CHAT_PROMPT_REQUIRED`
2. `AUTH_SESSION_REQUIRED`
3. `BYOK_KEY_REQUIRED`
4. `PLANNER_DECISION_INVALID`
5. `PLANNER_REQUESTED_BLOCKED_TOOL`
6. `TOOL_NOT_AVAILABLE_IN_CHAT_MODE`
7. `CHAT_ORCHESTRATION_FAILED`

### 导出

1. `EDIT_DRAFT_REQUIRED`

规则：

1. `HTTP` 错误统一走 `ErrorEnvelope`
2. `WS` 错误统一走 `error.occurred`
3. 错误码应可分支处理，消息只做展示

## 9. 前端状态机映射

### 9.1 Launchpad

`Launchpad` 当前主要依赖：

1. `GET /api/v1/projects`
2. `GET /health`
3. `POST /api/v1/projects`

核心映射：

1. 列表卡片主状态
   <- `project.summary_state`

### 9.2 Workspace

`Workspace` 当前主要依赖：

1. `summaryState`
   <- `workspace.summary_state` 或 `project.summary.updated`
2. `coreMediaSummary`
   <- `workspace.media_summary`
3. `coreRuntimeState`
   <- `workspace.runtime_state`
4. `coreCapabilities`
   <- `workspace.capabilities` 或 `capabilities.updated`
5. `activeTasks`
   <- `workspace.active_tasks` 或 `task.updated`
6. `editDraft`
   <- `workspace.edit_draft` 或 `edit_draft.updated`
7. `chatTurns`
   <- `workspace.chat_turns` 或 `chat.turn.created`
8. `exportResult`
   <- `export.completed`
9. `lastError`
   <- `HTTP ErrorEnvelope` 或 `error.occurred`

前端不应再依赖：

1. `project.workflow_state`
2. `task.updated` 中的 `workflow_state`

## 10. 一句话总结

`Core API/WS contract` 的本质是：

`用 Project + EditDraft + media_summary + runtime_state + capabilities + active_tasks 这组正交事实，取代过去单一 workflow_state 的粗粒度驱动。`
