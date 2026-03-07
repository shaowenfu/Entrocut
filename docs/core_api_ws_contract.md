# Core API/WS Contract

本文档定义当前重构阶段 `Client -> Core` 的最小本地契约：

1. `HTTP API contract（HTTP 接口契约）`
2. `WebSocket event contract（WebSocket 事件契约）`
3. `schema（数据结构）`
4. 错误语义
5. 与当前前端状态机的映射关系

目标不是一次性设计完整系统，而是支撑当前已经稳定下来的：

1. `Launchpad（启动台）` 状态机
2. `Workspace（工作台）` 状态机
3. 最小 `Chat-to-Cut` 本地闭环

## 1. 设计目标

当前 `Core contract` 只覆盖以下能力：

1. 健康检查与运行能力探测
2. 创建项目
3. 查询项目
4. 导入素材
5. 发送 chat
6. 导出项目
7. 订阅项目级事件流

当前明确 `Non-goals（非目标）`：

1. 不定义真实 `LLM provider（大模型供应商）` 细节
2. 不定义真实 `Embedding（向量化）` 细节
3. 不定义真实 `DashVector search（向量检索）` 细节
4. 不暴露内部 `FFmpeg` 实现细节
5. 不在 `Core API` 里泄露内部任务编排细节

## 2. 设计原则

1. 先定义契约，再替换实现
2. 前端只依赖稳定 `schema`
3. 后端通过统一 `task + event` 语义表达异步过程
4. 错误必须结构化，不能只返回裸字符串
5. `HTTP` 负责命令入口，`WebSocket` 负责过程推进与结果同步

## 3. Core 能力边界

`Core` 对前端暴露的本质能力只有两类：

1. 接受命令
   例如创建项目、导入素材、发送 chat、发起导出
2. 推送状态变化
   例如任务开始、任务进度、分镜更新、导出完成、失败

所以：

1. 不是所有结果都要同步阻塞返回
2. 绝大多数“过程中的变化”应走 `WebSocket`

## 4. 顶层资源模型

当前最小资源模型定义如下。

### 4.1 Project

```ts
interface Project {
  id: string;
  title: string;
  workflow_state:
    | "prompt_input_required"
    | "awaiting_media"
    | "media_ready"
    | "media_processing"
    | "chat_thinking"
    | "ready"
    | "rendering"
    | "failed";
  created_at: string;
  updated_at: string;
}
```

### 4.2 Asset

```ts
interface Asset {
  id: string;
  name: string;
  type: "video" | "audio";
  duration: string;
}
```

### 4.3 Clip

```ts
interface Clip {
  id: string;
  parent: string;
  start: string;
  end: string;
  score: string;
  desc: string;
  thumb_class?: string | null;
}
```

### 4.4 StoryboardScene

```ts
interface StoryboardScene {
  id: string;
  title: string;
  duration: string;
  intent: string;
  color_class?: string | null;
  bg_class?: string | null;
}
```

### 4.5 ChatTurn

```ts
type ChatTurn =
  | {
      id: string;
      role: "user";
      content: string;
      created_at: string;
    }
  | {
      id: string;
      role: "assistant";
      type: "decision";
      decision_type: "UPDATE_PROJECT_CONTRACT" | "APPLY_PATCH_ONLY" | "ASK_USER_CLARIFICATION";
      reasoning_summary: string;
      ops: AgentOperation[];
      created_at: string;
    };
```

### 4.6 Task

```ts
interface Task {
  id: string;
  type: "ingest" | "index" | "chat" | "render";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress?: number | null;
  message?: string | null;
  created_at: string;
  updated_at: string;
}
```

### 4.7 WorkspaceSnapshot

```ts
interface WorkspaceSnapshot {
  project: Project;
  assets: Asset[];
  clips: Clip[];
  storyboard: StoryboardScene[];
  chat_turns: ChatTurn[];
  active_task: Task | null;
}
```

这是当前前端真正需要的一次性完整读取对象。

## 5. 通用 Envelope

## 5.1 ErrorEnvelope

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

1. `code` 供前端分支判断
2. `message` 供用户展示
3. `details` 供调试和补充上下文
4. 不暴露内部实现栈

## 5.2 Success Envelope

当前 `HTTP` 可直接返回业务对象，不强制外层统一 `data` 包裹。  
原则是保持最小、直接、稳定。

## 6. HTTP API Contract

接口前缀统一为：

```text
/api/v1
```

## 6.1 Runtime

### `GET /health`

用途：

1. 启动台检测 `Core` 是否可用
2. 工作台健康轮询

响应示例：

```json
{
  "status": "ok",
  "service": "core",
  "version": "0.7.0",
  "phase": "clean_room_rewrite"
}
```

### `GET /api/v1/runtime/capabilities`

用途：

1. 前端探测当前 `Core` 支持哪些表面能力
2. 原型阶段可用于 `feature gating（能力开关）`

响应示例：

```json
{
  "service": "core",
  "version": "0.7.0",
  "phase": "clean_room_rewrite",
  "mode": "prototype_backed",
  "retained_surfaces": [
    "health",
    "projects",
    "project_events",
    "chat",
    "asset_import",
    "export"
  ]
}
```

## 6.2 Launchpad

### `GET /api/v1/projects`

用途：

1. 启动台加载最近项目

查询参数：

1. `limit` 可选，默认 `20`

响应示例：

```json
{
  "projects": [
    {
      "id": "proj_001",
      "title": "Japan Ski Trip",
      "workflow_state": "ready",
      "created_at": "2026-03-07T09:00:00Z",
      "updated_at": "2026-03-07T09:05:00Z"
    }
  ]
}
```

### `POST /api/v1/projects`

用途：

1. 创建空项目
2. 用 `prompt`
3. 用 `prompt + 素材引用`

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

1. `prompt` 和 `media` 至少要有一个
2. 真实实现里，浏览器环境文件对象不会直接通过 HTTP 发二进制；这里约定的是“媒体引用”

响应：

```json
{
  "project": {
    "id": "proj_001",
    "title": "Japan Ski Trip",
    "workflow_state": "media_ready",
    "created_at": "2026-03-07T09:00:00Z",
    "updated_at": "2026-03-07T09:00:00Z"
  },
  "workspace": {
    "project": {
      "id": "proj_001",
      "title": "Japan Ski Trip",
      "workflow_state": "media_ready",
      "created_at": "2026-03-07T09:00:00Z",
      "updated_at": "2026-03-07T09:00:00Z"
    },
    "assets": [],
    "clips": [],
    "storyboard": [],
    "chat_turns": [],
    "active_task": null
  }
}
```

为什么创建项目时直接返回 `workspace snapshot`：

1. 启动台创建后会立即进入工作台
2. 避免前端再多打一跳查询

## 6.3 Workspace

### `GET /api/v1/projects/{project_id}`

用途：

1. 工作台初始化读取
2. 刷新当前项目完整状态

响应：

```json
{
  "workspace": {
    "project": {
      "id": "proj_001",
      "title": "Japan Ski Trip",
      "workflow_state": "ready",
      "created_at": "2026-03-07T09:00:00Z",
      "updated_at": "2026-03-07T09:10:00Z"
    },
    "assets": [],
    "clips": [],
    "storyboard": [],
    "chat_turns": [],
    "active_task": null
  }
}
```

### `POST /api/v1/projects/{project_id}/assets:import`

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
    "type": "ingest",
    "status": "queued",
    "progress": 0,
    "message": "Media ingest queued",
    "created_at": "2026-03-07T09:10:00Z",
    "updated_at": "2026-03-07T09:10:00Z"
  }
}
```

说明：

1. 这是异步任务入口，不同步返回最终结果
2. 真正的推进和结果通过 `WS event stream`

### `POST /api/v1/projects/{project_id}/chat`

用途：

1. 发送用户 chat 指令

请求：

```ts
interface ChatRequest {
  prompt: string;
}
```

响应：

```json
{
  "task": {
    "id": "task_chat_001",
    "type": "chat",
    "status": "queued",
    "progress": null,
    "message": "Chat queued",
    "created_at": "2026-03-07T09:12:00Z",
    "updated_at": "2026-03-07T09:12:00Z"
  }
}
```

说明：

1. 前端发出命令后立刻切 `chatState -> responding`
2. 最终结果由 `WS` 推送：`chat turn + storyboard patch + task status`

### `POST /api/v1/projects/{project_id}/export`

用途：

1. 触发导出

请求：

```ts
interface ExportRequest {
  format?: string;
  quality?: string;
}
```

响应：

```json
{
  "task": {
    "id": "task_render_001",
    "type": "render",
    "status": "queued",
    "progress": 0,
    "message": "Export queued",
    "created_at": "2026-03-07T09:15:00Z",
    "updated_at": "2026-03-07T09:15:00Z"
  }
}
```

## 7. WebSocket Event Contract

连接地址：

```text
GET /api/v1/projects/{project_id}/events
```

`WebSocket` 只负责项目级实时事件，不承担命令入口。

## 7.1 EventEnvelope

```ts
interface EventEnvelope<T = unknown> {
  sequence: number;
  event: string;
  project_id: string;
  emitted_at: string;
  data: T;
}
```

字段说明：

1. `sequence`
   单项目内严格递增，用于重连恢复
2. `event`
   事件类型
3. `project_id`
   项目标识
4. `emitted_at`
   事件发出时间
5. `data`
   事件载荷

## 7.2 事件类型

当前最小事件集合如下。

### `workspace.snapshot`

用途：

1. 连接建立后一次性推送当前完整状态
2. 重连后重同步

```json
{
  "sequence": 1,
  "event": "workspace.snapshot",
  "project_id": "proj_001",
  "emitted_at": "2026-03-07T09:00:00Z",
  "data": {
    "workspace": {
      "project": {
        "id": "proj_001",
        "title": "Japan Ski Trip",
        "workflow_state": "ready",
        "created_at": "2026-03-07T09:00:00Z",
        "updated_at": "2026-03-07T09:05:00Z"
      },
      "assets": [],
      "clips": [],
      "storyboard": [],
      "chat_turns": [],
      "active_task": null
    }
  }
}
```

### `task.updated`

用途：

1. 通知任务状态变化
2. 驱动前端 `activeTask`

```ts
interface TaskUpdatedEventData {
  task: Task;
  workflow_state: Project["workflow_state"];
}
```

示例：

```json
{
  "sequence": 11,
  "event": "task.updated",
  "project_id": "proj_001",
  "emitted_at": "2026-03-07T09:12:03Z",
  "data": {
    "task": {
      "id": "task_chat_001",
      "type": "chat",
      "status": "running",
      "progress": null,
      "message": "Analyzing footage and generating edit...",
      "created_at": "2026-03-07T09:12:00Z",
      "updated_at": "2026-03-07T09:12:03Z"
    },
    "workflow_state": "chat_thinking"
  }
}
```

### `chat.turn.created`

用途：

1. 推送新的用户消息或 `assistant` 决策消息

```ts
interface ChatTurnCreatedEventData {
  turn: ChatTurn;
}
```

### `storyboard.updated`

用途：

1. 推送最新分镜结果

```ts
interface StoryboardUpdatedEventData {
  storyboard: StoryboardScene[];
}
```

### `assets.updated`

用途：

1. 推送素材和片段变化

```ts
interface AssetsUpdatedEventData {
  assets: Asset[];
  clips: Clip[];
}
```

### `project.updated`

用途：

1. 推送项目元信息和 `workflow_state`

```ts
interface ProjectUpdatedEventData {
  project: Project;
}
```

### `export.completed`

用途：

1. 推送导出完成结果

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

### `error.occurred`

用途：

1. 推送流程级错误

```ts
interface ErrorOccurredEventData {
  code: string;
  message: string;
  task_id?: string | null;
  recoverable: boolean;
  workflow_state: Project["workflow_state"];
}
```

## 8. HTTP 与 WS 的职责分工

最佳实践是：

1. `HTTP` 只做“命令入口”和“快照读取”
2. `WS` 只做“状态推进”和“结果广播”

具体分工：

### HTTP 负责

1. 创建项目
2. 获取项目快照
3. 发起导入
4. 发起 chat
5. 发起导出

### WS 负责

1. 推任务状态
2. 推分镜更新
3. 推素材更新
4. 推 chat 消息
5. 推导出完成
6. 推流程错误

## 9. 错误语义

推荐最小错误码集合如下。

### 通用

1. `INVALID_REQUEST`
2. `RESOURCE_NOT_FOUND`
3. `WORKSPACE_NOT_READY`
4. `CONFLICTING_TASK_ALREADY_RUNNING`
5. `INTERNAL_ERROR`

### 素材导入

1. `MEDIA_INPUT_REQUIRED`
2. `MEDIA_PATH_NOT_FOUND`
3. `UNSUPPORTED_MEDIA_TYPE`
4. `INGEST_FAILED`

### Chat

1. `PROMPT_REQUIRED`
2. `CHAT_ALREADY_RUNNING`
3. `CHAT_FAILED`

### 导出

1. `EXPORT_ALREADY_RUNNING`
2. `EXPORT_FAILED`

错误返回示例：

```json
{
  "error": {
    "code": "CONFLICTING_TASK_ALREADY_RUNNING",
    "message": "Another task is already running for this project.",
    "details": {
      "project_id": "proj_001",
      "active_task_type": "chat"
    },
    "request_id": "req_ab12cd34ef56"
  }
}
```

## 10. 前端状态机映射

## 10.1 Launchpad

`Launchpad` 对 `Core` 的依赖映射：

1. `projectsLoadState`
   <- `GET /api/v1/projects`
2. `systemStatus`
   <- `GET /health`
3. `createState / importState`
   <- `POST /api/v1/projects`
4. `navigationState`
   <- 创建成功后前端本地跳转

## 10.2 Workspace

`Workspace` 对 `Core` 的依赖映射：

1. `loadState`
   <- `GET /api/v1/projects/{project_id}` 或 `workspace.snapshot`
2. `workflowState`
   <- `project.updated` / `task.updated`
3. `chatState`
   <- `task.updated` 中 `type=chat`
4. `activeTask`
   <- `task.updated`
5. `assets / clips`
   <- `assets.updated`
6. `storyboard`
   <- `storyboard.updated`
7. `chatTurns`
   <- `chat.turn.created`
8. `exportResult`
   <- `export.completed`
9. `lastError`
   <- `HTTP ErrorEnvelope` 或 `error.occurred`

## 11. 最小实现建议

为了避免再次偏航，建议按这个顺序落地：

1. 先在 `core/server.py` 定义 `Pydantic schema`
2. 先实现：
   - `GET /api/v1/projects`
   - `POST /api/v1/projects`
   - `GET /api/v1/projects/{project_id}`
   - `POST /api/v1/projects/{project_id}/chat`
   - `WS /api/v1/projects/{project_id}/events`
3. 先用 `in-memory（内存态）` 或极简本地存储
4. 先用假任务和假事件，把前端闭环跑通
5. 再替换为真实 `ingest / chat / export` 实现

## 12. 一句话总结

`Core API/WS contract` 的本质是：

把当前已经稳定下来的前端状态机，翻译成 `Core` 必须提供的最小命令入口、快照读取和事件流语义。
