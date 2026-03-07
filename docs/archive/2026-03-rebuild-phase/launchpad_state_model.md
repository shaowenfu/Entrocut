# Launchpad State Model

本文档定义 `Launchpad（启动台）` 的：

1. 状态切换表
2. `state model（状态模型）`
3. `event -> reducer（事件到状态更新规则）`

目标是让当前 `prototype mode（原型模式）` 的启动台行为有清晰边界，并为后续 `Core API/WS contract（本地 API/事件契约）` 提供落点。

## 1. 核心功能

`Launchpad` 当前只关注以下流程：

1. 加载最近项目
2. 检查本地 `Core` 是否可用
3. 创建空项目
4. 选择素材并创建项目
5. 用 `prompt（提示词）` 创建项目
6. 创建成功后进入 `Workspace（工作台）`
7. 创建失败后给出错误

## 2. 状态模型

```ts
type LoadState = "idle" | "loading" | "ready" | "failed";
type SystemStatus = "connecting" | "ready" | "error";
type CreateState = "idle" | "creating" | "failed";
type ImportState = "idle" | "picking_media" | "importing" | "failed";
type NavigationState = "idle" | "entering_workspace" | "failed";

interface LaunchpadState {
  recentProjects: ProjectMeta[];

  projectsLoadState: LoadState;
  systemStatus: SystemStatus;
  createState: CreateState;
  importState: ImportState;
  navigationState: NavigationState;

  activeWorkspaceId: string | null;
  activeWorkspaceName: string | null;
  lastError: LaunchpadError | null;
}
```

设计原则：

1. 一个状态只表达一类流程
2. 不再依赖多个分散的 `boolean（布尔值）`
3. 页面是否可操作从状态派生，不重复存储

## 3. 派生规则

以下能力应从状态派生，而不是再存成新字段：

```ts
const isBusy =
  createState === "creating" ||
  importState === "picking_media" ||
  importState === "importing" ||
  navigationState === "entering_workspace";

const canCreateEmptyProject =
  systemStatus === "ready" &&
  createState === "idle" &&
  importState === "idle" &&
  navigationState === "idle";

const canImportMedia =
  systemStatus === "ready" &&
  createState === "idle" &&
  importState === "idle" &&
  navigationState === "idle";

const showProjectsLoading = projectsLoadState === "loading";
const showSystemError = systemStatus === "error";
```

## 4. 状态切换表

### 4.1 加载最近项目

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `idle` | 进入启动台页面 | `loading` | 显示项目 loading |
| `loading` | 加载成功 | `ready` | 显示项目列表 |
| `loading` | 加载失败 | `failed` | 显示错误和重试 |
| `failed` | 用户刷新 | `loading` | 重新拉取项目 |
| `ready` | 用户刷新 | `loading` | 保留旧列表并刷新 |

### 4.2 检查本地 Core

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `connecting` | 健康检查成功 | `ready` | 可执行创建/导入 |
| `connecting` | 健康检查失败 | `error` | 显示服务不可用 |
| `error` | 用户重试 | `connecting` | 显示重试中 |
| `ready` | 后续检查失败 | `error` | 显示服务断开 |

当前原型还没有真实健康检查动作，因此在 `prototype mode` 下可直接保持 `ready`。

### 4.3 创建空项目

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `idle` | 点击 `Create Empty Project` | `creating` | 禁用重复点击 |
| `creating` | 创建成功 | `idle` | 准备进入 `Workspace` |
| `creating` | 创建失败 | `failed` | 显示错误 |
| `failed` | 再次点击创建 | `creating` | 重新创建 |

### 4.4 选择素材并创建

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `idle` | 点击浏览素材 | `picking_media` | 打开系统选择器 |
| `picking_media` | 用户取消 | `idle` | 安静返回，不报错 |
| `picking_media` | 选择成功 | `importing` | 显示导入中 |
| `importing` | 创建成功 | `idle` | 准备进入 `Workspace` |
| `importing` | 导入或创建失败 | `failed` | 显示错误 |
| `failed` | 再次浏览素材 | `picking_media` | 重新选择素材 |

### 4.5 进入 Workspace

| 当前状态 | 触发事件 | 下一状态 | UI 表现 |
|---|---|---|---|
| `idle` | 拿到 `projectId` | `entering_workspace` | 页面准备切换 |
| `entering_workspace` | 跳转完成 | `idle` | 工作台接管 |
| `entering_workspace` | 跳转失败 | `failed` | 显示错误 |

## 5. 事件定义

```ts
type LaunchpadEvent =
  | { type: "PROJECTS_LOAD_STARTED" }
  | { type: "PROJECTS_LOAD_SUCCEEDED"; projects: ProjectMeta[] }
  | { type: "PROJECTS_LOAD_FAILED"; error: LaunchpadError }
  | { type: "SYSTEM_CHECK_STARTED" }
  | { type: "SYSTEM_CHECK_SUCCEEDED" }
  | { type: "SYSTEM_CHECK_FAILED" }
  | { type: "CREATE_STARTED" }
  | { type: "CREATE_SUCCEEDED"; projectId: string; projectName: string }
  | { type: "CREATE_FAILED"; error: LaunchpadError }
  | { type: "MEDIA_PICK_STARTED" }
  | { type: "MEDIA_PICK_CANCELLED" }
  | { type: "MEDIA_PICK_SUCCEEDED" }
  | { type: "IMPORT_STARTED" }
  | { type: "IMPORT_FAILED"; error: LaunchpadError }
  | { type: "NAVIGATION_STARTED" }
  | { type: "NAVIGATION_SUCCEEDED" }
  | { type: "NAVIGATION_FAILED"; error: LaunchpadError }
  | { type: "CLEAR_ERROR" };
```

## 6. Event -> Reducer 规则

### 项目列表

1. `PROJECTS_LOAD_STARTED`
   - `projectsLoadState = "loading"`
   - `lastError = null`
2. `PROJECTS_LOAD_SUCCEEDED`
   - `projectsLoadState = "ready"`
   - `recentProjects = event.projects`
3. `PROJECTS_LOAD_FAILED`
   - `projectsLoadState = "failed"`
   - `recentProjects = []`
   - `lastError = event.error`

### 系统可用性

1. `SYSTEM_CHECK_STARTED`
   - `systemStatus = "connecting"`
2. `SYSTEM_CHECK_SUCCEEDED`
   - `systemStatus = "ready"`
3. `SYSTEM_CHECK_FAILED`
   - `systemStatus = "error"`

### 创建项目

1. `CREATE_STARTED`
   - `createState = "creating"`
   - `lastError = null`
2. `CREATE_SUCCEEDED`
   - `createState = "idle"`
   - `importState = "idle"`
   - `activeWorkspaceId = event.projectId`
   - `activeWorkspaceName = event.projectName`
3. `CREATE_FAILED`
   - `createState = "failed"`
   - `importState = "failed"` 仅在导入建项目流程里使用
   - `lastError = event.error`

### 选择与导入素材

1. `MEDIA_PICK_STARTED`
   - `importState = "picking_media"`
   - `lastError = null`
2. `MEDIA_PICK_CANCELLED`
   - `importState = "idle"`
3. `MEDIA_PICK_SUCCEEDED`
   - `importState = "importing"`
4. `IMPORT_STARTED`
   - `importState = "importing"`
   - `lastError = null`
5. `IMPORT_FAILED`
   - `importState = "failed"`
   - `lastError = event.error`

### 页面切换

1. `NAVIGATION_STARTED`
   - `navigationState = "entering_workspace"`
2. `NAVIGATION_SUCCEEDED`
   - `navigationState = "idle"`
3. `NAVIGATION_FAILED`
   - `navigationState = "failed"`
   - `lastError = event.error`

### 通用

1. `CLEAR_ERROR`
   - `lastError = null`

## 7. 当前关键约束

1. `createState === "creating"` 时，禁止重复创建
2. `importState === "picking_media" | "importing"` 时，禁止重复导入
3. 用户取消素材选择，不进入失败态
4. 只有拿到合法 `projectId` 后，才能进入 `navigation`
5. 若未来接入真实 `Core`，`systemStatus !== "ready"` 时，创建和导入都应禁用或立即失败

## 8. 落地说明

`useLaunchpadStore.ts` 应围绕这套事件和 `reducer` 工作：

1. 异步动作负责发事件
2. `reducer` 负责更新状态
3. 页面只消费状态和动作，不自己拼流程
