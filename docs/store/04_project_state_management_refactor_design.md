# Project State Management Refactor Design

本文档重新定义 `EntroCut` 的项目状态管理。

目标不是给现有 `workflow_state` 换一组更顺眼的名字，而是从第一性原理重新回答：

1. 项目状态管理到底在解决什么问题
2. 哪些状态是真实业务事实
3. 哪些状态只是过程信息
4. 哪些状态应该提供给 `agent`、`client` 和 `WebSocket event stream`

本文档同时承接：

1. [README.md](../../README.md) 中 `Chat-to-Cut` 的系统目标
2. [EntroCut_algorithm.md](../../EntroCut_algorithm.md) 中 `select -> compose -> evaluate -> revise` 的闭环
3. [EntroCut_architecture.md](../../EntroCut_architecture.md) 中 `Core` 作为本地权威状态层的定位
4. [03_state_layer_design.md](../agent_runtime/03_state_layer_design.md) 中 `Goal / Draft / Selection / Retrieval / Execution / Conversation` 六类运行时状态

---

## 1. 问题定义

当前实现把下列信息压进了单一 `Project.workflow_state`：

1. 素材是否存在
2. 素材是否处理中
3. `chat agent` 是否在运行
4. 草案是否已经有内容
5. 是否正在导出
6. 是否发生过失败

当前枚举见 [core/schemas.py](/home/sherwen/MyProjects/Entrocut/core/schemas.py)：

1. `prompt_input_required`
2. `awaiting_media`
3. `media_ready`
4. `media_processing`
5. `chat_thinking`
6. `ready`
7. `rendering`
8. `failed`

这会造成 4 类根本性问题：

### 1.1 混淆了不同维度的事实

这些状态并不属于一个维度：

1. `awaiting_media / media_ready` 是资源可用性
2. `media_processing / chat_thinking / rendering` 是运行过程
3. `ready / failed` 是结果判断

它们天然不互斥，因此单枚举无法正确表达真实世界。

### 1.2 无法表示并发事实

例如以下场景都是真实且合理的：

1. 素材仍在切分和向量化，但用户已经可以开始意图澄清
2. 部分素材已完成索引，`retrieve` 已可用，剩余素材仍在处理中
3. 导出正在运行，但用户仍然可以继续对下一版草案对话

当前单一 `workflow_state + active_task` 无法表达这些并发状态。

### 1.3 错把项目当作流程节点

`Project` 本质上是工作容器，不是进度条。

真正的状态事实分散在不同对象上：

1. 素材处理状态属于 `asset` 或其处理任务
2. 草案内容状态属于 `EditDraft`
3. `agent` 执行状态属于 `runtime / task`
4. 导出状态属于 `export task / export artifact`

把这些状态都挂到 `Project`，会让 `Project` 成为无边界杂物箱。

### 1.4 阻碍了 `planning-first` 的产品目标

当前 `create_project` 要求 `title / prompt / media` 至少有一个存在，这和产品目标不一致。

如果系统允许用户先通过对话澄清需求，再决定是否导入素材，那么：

1. 空项目必须是合法状态
2. `chat` 在无素材时也必须可用
3. 只是此时 `retrieve` 等依赖素材索引的工具不可用

---

## 2. 第一性原理

项目状态管理的本质不是“给项目打一串状态值”，而是稳定回答 3 个问题：

1. 当前有哪些事实是真的
2. 当前系统允许做什么动作
3. 当前用户应该看到什么反馈

从这 3 个问题直接推出 3 条设计原则。

### 2.1 先保存事实，再派生能力，最后再派生展示状态

正确顺序应该是：

`world facts -> capabilities -> presentation summary`

而不是直接发明一个总状态让所有层去猜。

### 2.2 状态属于拥有该事实的实体

状态应绑定到真实的业务对象：

1. 素材处理属于 `asset`
2. 草案内容属于 `EditDraft`
3. 运行时目标、焦点、检索候选、执行轨迹属于 `project runtime state`
4. 导出属于 `export task`
5. 单次过程推进属于 `task`

### 2.3 单一总状态只能是派生视图，不能是权威事实源

如果仍然需要在 `Launchpad` 或项目卡片上显示一个简短标签，可以保留一个派生的 `summary_state`。

但它只能服务：

1. 列表展示
2. 粗粒度筛选
3. 人类快速扫视

不能再驱动：

1. 接口准入
2. 工具 gating
3. `agent` 决策
4. 数据持久化主逻辑

---

## 3. 备选方案

### 3.1 方案 A：保留单一 `workflow_state`，只调整枚举名称

做法：

1. 把旧枚举替换成更贴切的新名字
2. 继续由 `Project` 持有唯一状态

优点：

1. 改动最小
2. 前端兼容成本最低

缺点：

1. 本质问题不变
2. 无法表达并发事实
3. `agent` 仍然拿不到真正可消费的状态

结论：

`不推荐。`

### 3.2 方案 B：不再定义显式状态，只从 `task + data` 临时推断

做法：

1. 删除 `workflow_state`
2. 所有界面和运行逻辑都从 `assets / tasks / draft / chat_turns` 临时推导

优点：

1. 避免重复字段
2. 理论上更“纯”

缺点：

1. 推导逻辑会散落在 `client / core / planner context` 多处
2. UI 和 `agent` 的行为会依赖隐式推断，难以复用
3. `goal / retrieval / execution / conversation` 这类运行时状态无处安放

结论：

`不推荐。`

### 3.3 方案 C：实体归属明确的多轴状态模型

做法：

1. 拆掉 `Project.workflow_state` 这个权威单轴状态
2. 把状态分配到 `asset / draft / runtime / task / export`
3. 显式派生 `capabilities`
4. 如有需要，再派生单一 `summary_state`

优点：

1. 符合第一性原理
2. 能表达并发与部分就绪
3. 天然契合当前 `agent runtime` 设计
4. 更适合 `SQLite`、事件流和前端状态订阅

缺点：

1. 需要一次结构性迁移
2. 需要前后端共同改造读取方式

结论：

`推荐采用。`

---

## 4. 推荐设计总览

推荐把项目状态管理拆成 5 层：

1. `Project Metadata`
2. `Asset Processing State`
3. `EditDraft State`
4. `Project Runtime State`
5. `Task / Job State`

然后由这些事实派生两类输出：

1. `ProjectCapabilities`
2. `ProjectSummaryState`

一句话：

`状态按实体归属，能力按事实派生，展示摘要最后生成。`

---

## 5. Project 不再承担业务流程状态

### 5.1 Project 只保留容器级元数据

推荐把 `ProjectModel` 收缩成：

```python
class ProjectModel(BaseModel):
    id: str
    title: str
    lifecycle_state: Literal["active", "archived"] = "active"
    created_at: str
    updated_at: str
```

说明：

1. `Project` 只负责“这个项目是什么”
2. 不再负责“这个项目现在正在经历什么过程”

### 5.2 空项目必须合法

`create_project` 应允许 `title / prompt / media` 全部为空。

建议行为：

1. 若 `title` 为空，自动创建 `Untitled Project`
2. 创建空 `EditDraft`
3. 创建空 `ProjectRuntimeState`
4. `chat` 立即可用
5. `retrieve / inspect / export` 依据 capability 决定是否可用

这和 `planning-first` 的产品方向一致：

`先澄清 intent，再决定是否进入素材驱动的编辑闭环。`

---

## 6. Asset State：素材状态属于 asset，不属于 project

### 6.1 权威事实应落在 asset 级别

如果一个项目有多个素材，真正的事实是：

1. 有些素材已引用但还未处理
2. 有些素材正在切分
3. 有些素材切分完成但还未向量化
4. 有些素材已完全可检索
5. 有些素材失败，需要重试

这类事实必须挂在 `asset` 上，而不是压成项目级一个值。

### 6.2 推荐的 asset 处理状态

MVP 阶段建议每个 `asset` 至少拥有一个线性处理阶段：

```python
AssetProcessingStage = Literal[
    "pending",
    "segmenting",
    "vectorizing",
    "ready",
    "failed",
]
```

并配合以下事实字段：

```python
class AssetProcessingState(BaseModel):
    stage: AssetProcessingStage
    progress: int | None = None
    clip_count: int = 0
    indexed_clip_count: int = 0
    last_error: dict[str, Any] | None = None
    updated_at: str
```

### 6.3 项目级 media summary 只做聚合

项目层不保存单一 `media_state` 作为权威事实，而是聚合出：

```python
class ProjectMediaSummary(BaseModel):
    asset_count: int
    pending_asset_count: int
    processing_asset_count: int
    ready_asset_count: int
    failed_asset_count: int
    total_clip_count: int
    indexed_clip_count: int
    retrieval_ready: bool
```

关键判断：

1. `asset_count == 0` 不代表项目不可聊天，只代表素材池为空
2. `retrieval_ready == True` 的最小条件应是“至少存在一批已向量化并可检索的 `clip`”
3. 如果只有部分素材就绪，也允许进入基于现有候选池的编辑

---

## 7. EditDraft State：草案只表达内容事实，不表达过程状态

### 7.1 当前问题

当前 `EditDraft.status` 包含：

1. `draft`
2. `ready`
3. `rendering`
4. `failed`

其中：

1. `rendering` 属于导出过程，不属于草案本体
2. `failed` 往往是任务失败，不一定意味着草案失效

### 7.2 推荐原则

`EditDraft` 只保存当前可编辑内容事实：

1. 当前 `shots / scenes`
2. 当前版本号
3. 当前选区
4. 当前更新时间

是否可导出，应由事实推导：

1. 是否存在有效 `shot`
2. 是否存在必要素材引用
3. 是否有阻塞性任务

### 7.3 推荐方向

短期：

1. 停止把 `rendering / failed` 写进 `EditDraft.status`
2. `EditDraft.status` 仅保留极少语义，如 `draft`

长期：

1. 删除 `EditDraft.status`
2. 统一通过 `draft_summary + capabilities` 表达“当前是否可评审 / 可导出”

---

## 8. Project Runtime State：让 agent 真正有状态可读

这一层承接 [03_state_layer_design.md](../agent_runtime/03_state_layer_design.md) 的六类状态，并作为每个项目的持久化工作记忆。

### 8.1 为什么必须单独存在

如果没有这层，系统只能在以下两个极端之间摆动：

1. 靠原始聊天记录硬猜意图
2. 靠 `workflow_state` 这种粗糙字段硬猜下一步

这两种方式都不足以支撑 `planning-first` 的 `agent loop`。

### 8.2 推荐的 runtime 子状态

```python
class ProjectRuntimeState(BaseModel):
    goal_state: GoalState
    focus_state: FocusState
    conversation_state: ConversationState
    retrieval_state: RetrievalState
    execution_state: ExecutionState
    updated_at: str
```

建议定义如下。

#### GoalState

回答：

1. 用户当前到底想做什么
2. 哪些约束已确认
3. 哪些问题还没明确

```python
class GoalState(BaseModel):
    brief: str | None = None
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    updated_at: str
```

#### FocusState

回答：

1. 这轮对话作用于 `project / scene / shot` 哪个层级
2. 当前焦点对象是谁

```python
class FocusState(BaseModel):
    scope_type: Literal["project", "scene", "shot"] = "project"
    scene_id: str | None = None
    shot_id: str | None = None
    updated_at: str
```

#### ConversationState

回答：

1. 最近用户是在澄清、确认还是否定
2. 当前是否存在待回答问题
3. 哪些共识已经沉淀成工作事实

```python
class ConversationState(BaseModel):
    pending_questions: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    latest_user_feedback: Literal["unknown", "clarify", "approve", "reject", "revise"] = "unknown"
    updated_at: str
```

#### RetrievalState

回答：

1. 最近一次在找什么
2. 候选池是否存在
3. 当前为什么不能检索

```python
class RetrievalState(BaseModel):
    last_query: str | None = None
    candidate_clip_ids: list[str] = Field(default_factory=list)
    retrieval_ready: bool = False
    blocking_reason: str | None = None
    updated_at: str
```

#### ExecutionState

回答：

1. `agent` 最近做了什么
2. 当前有没有在跑
3. 最近一次失败是什么

```python
class ExecutionState(BaseModel):
    agent_run_state: Literal["idle", "planning", "executing_tool", "waiting_user", "failed"] = "idle"
    current_task_id: str | None = None
    last_tool_name: str | None = None
    last_error: dict[str, Any] | None = None
    updated_at: str
```

### 8.3 关键判断

`ProjectRuntimeState` 不是数据库镜像，也不是模型思维链。

它只保存“下一步决策明显依赖的结构化事实”。

---

## 9. Task / Job State：过程状态应由任务承担，而不是 project.active_task

### 9.1 当前问题

当前只有一个 `active_task`，这隐含了错误假设：

`一个项目同一时刻只能有一个重要过程。`

这与真实需求冲突。

### 9.2 推荐方向

改成：

1. `tasks` 作为事实表
2. `WorkspaceSnapshot` 暴露 `active_tasks`
3. 每个任务增加 `slot`

```python
TaskSlot = Literal["media", "agent", "export"]

class TaskModel(BaseModel):
    id: str
    slot: TaskSlot
    type: Literal["ingest", "index", "chat", "render"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    owner_type: Literal["project", "asset", "draft"]
    owner_id: str
    progress: int | None = None
    message: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str
```

### 9.3 并发策略

建议明确以下并发约束：

1. 同一项目允许多个 `media` 任务并存
2. 同一项目同时只允许一个 `agent` 运行任务
3. 同一项目同时只允许一个 `export` 任务
4. `media` 任务可以与 `agent` 的纯规划对话并行
5. `export` 应绑定到某个明确 `draft version`，避免“导出中的草案还在被改”

这比用一个 `active_task` 粗暴锁死全部行为更合理。

---

## 10. Capabilities：动作准入应显式派生

### 10.1 为什么要有 capabilities

用户界面和 `agent` 真正关心的不是“项目总状态是什么”，而是：

1. 能不能发起聊天
2. 这次聊天是不是只能做需求澄清
3. 能不能调用 `retrieve`
4. 能不能导出

这些都应该由事实推导成显式 capability。

### 10.2 推荐 capability 模型

```python
class ProjectCapabilities(BaseModel):
    can_send_chat: bool
    chat_mode: Literal["planning_only", "editing"]
    can_retrieve: bool
    can_inspect: bool
    can_patch_draft: bool
    can_preview: bool
    can_export: bool
    blocking_reasons: list[str] = Field(default_factory=list)
```

### 10.3 推荐派生规则

#### 空项目

1. `can_send_chat = True`
2. `chat_mode = planning_only`
3. `can_retrieve = False`
4. `can_export = False`

#### 有素材但未索引完成

1. `can_send_chat = True`
2. `chat_mode = planning_only`
3. `can_retrieve = False`
4. `blocking_reasons` 包含 `media_index_not_ready`

#### 至少有一批素材已检索可用

1. `can_send_chat = True`
2. `chat_mode = editing`
3. `can_retrieve = True`

#### 存在有效 `shots`

1. `can_preview = True`
2. `can_export = True`

### 10.4 对 agent 的含义

`planner` 不应再通过 `workflow_state == "media_ready"` 这类粗判断来猜自己能不能检索。

应该直接读取：

1. `chat_mode`
2. `can_retrieve`
3. `blocking_reasons`

这样无素材时它可以自然进入：

`clarify goal -> accumulate constraints -> wait for media`

而不是直接报错退出。

---

## 11. Summary State：单一状态只保留为展示摘要

如果前端列表仍然需要一个单一标签，建议保留一个非权威字段：

```python
ProjectSummaryState = Literal[
    "blank",
    "planning",
    "media_processing",
    "editing",
    "exporting",
    "attention_required",
]
```

注意：

1. 这是给人看的摘要，不是逻辑事实源
2. 它应由 `capabilities + active_tasks + errors` 派生
3. 它可以丢信息，因为它的职责只是摘要

推荐优先级：

1. 若 `export` 任务运行中，显示 `exporting`
2. 若存在阻塞性失败，显示 `attention_required`
3. 若存在 `media` 任务运行中且尚不可检索，显示 `media_processing`
4. 若 `chat_mode == planning_only`，显示 `planning`
5. 若 `chat_mode == editing`，显示 `editing`
6. 若没有任何目标与素材，显示 `blank`

---

## 12. 对当前 agent 设计的具体影响

### 12.1 `create_project`

应改为：

1. 永远允许创建
2. 初始化空 `GoalState`
3. 初始化空 `ConversationState`
4. 初始化空 `ProjectMediaSummary`
5. 派生出 `chat_mode = planning_only`

### 12.2 `queue_chat`

不再因为“没有素材”而直接报 `MEDIA_REQUIRED_FOR_CHAT`。

应改为：

1. 允许进入 `chat`
2. 若 `can_retrieve == False`，则 `planner` 只能做澄清、规划、总结或等待素材
3. `tool dispatcher` 在程序侧再次校验 capability，防止模型误调 `retrieve`

### 12.3 `build_planner_context_packet`

当前只给出 `project.workflow_state`，这远远不够。

建议扩展为至少注入：

1. `media_summary`
2. `project_capabilities`
3. `goal_state`
4. `focus_state`
5. `conversation_state`
6. `retrieval_state`
7. `execution_state`

这样 `planner` 才能判断：

1. 现在是该澄清还是该检索
2. 当前有没有候选池
3. 当前修改应作用到哪里
4. 最近失败发生在哪一步

### 12.4 `tool gating`

推荐规则：

1. `read` 永远可用
2. `retrieve` 仅在 `can_retrieve == True` 时可用
3. `inspect` 仅在存在候选池时可用
4. `patch` 仅在存在足够证据或明确草案操作目标时可用
5. `preview / export` 仅在存在可执行 `shots` 时可用

---

## 13. 对 API / WS Contract 的建议调整

### 13.1 Project 资源

`Project` 不再暴露 `workflow_state` 作为核心字段。

替代方案：

1. `project` 只保留元数据
2. `workspace` 新增：
   - `media_summary`
   - `runtime_state`
   - `capabilities`
   - `active_tasks`
   - 可选 `summary_state`

### 13.2 WebSocket event

建议新增或强化以下事件：

1. `asset.updated`
2. `runtime_state.updated`
3. `capabilities.updated`
4. `task.updated`
5. `project.summary.updated`

原则：

1. `task.updated` 负责过程
2. `runtime_state.updated` 负责工作记忆
3. `capabilities.updated` 负责动作可用性
4. `project.summary.updated` 仅负责列表显示

---

## 14. 对 SQLite 的建议调整

### 14.1 `projects`

去掉 `workflow_state`，改为纯元数据。

短期兼容期可保留，但标记为 `deprecated`。

### 14.2 `project_runtime`

从当前轻量表扩展为真正的运行时状态承载层。

建议新增：

1. `runtime_state_json`
2. `summary_state`
3. `updated_at`

### 14.3 `tasks`

建议新增：

1. `slot`
2. `owner_type`
3. `owner_id`
4. `result_json`
5. `error_json`

### 14.4 `assets`

建议新增：

1. `processing_stage`
2. `processing_progress`
3. `clip_count`
4. `indexed_clip_count`
5. `last_error_json`
6. `updated_at`

---

## 15. 迁移策略

### Phase 1：先纠正建模，不强求一次删干净

1. 允许空项目创建
2. 引入 `ProjectRuntimeState`
3. 引入 `ProjectCapabilities`
4. `queue_chat` 改为支持 `planning_only`
5. `workflow_state` 保留为派生兼容字段

### Phase 2：前端改读新状态

1. `Workspace` 改读 `capabilities / runtime_state / active_tasks`
2. 不再依赖 `workflow_state` 做准入判断
3. 聊天框根据 `chat_mode` 动态展示提示

### Phase 3：拆掉错误归属

1. 去掉 `active_task`
2. 去掉 `EditDraft.status` 里的 `rendering / failed`
3. 去掉 `Project.workflow_state` 的权威地位

### Phase 4：把 agent 真正接到状态层

1. `planner context` 直接读取 `runtime_state`
2. `tool observation` 回写 `retrieval_state / execution_state / conversation_state`
3. `focus_state` 从一次性请求参数升级成持久化工作事实

---

## 16. Non-goals

本次状态重构明确不做：

1. 不在这一轮把全部 `task orchestration（任务编排）` 做成通用工作流引擎
2. 不在这一轮引入复杂权限模型
3. 不在这一轮设计多人协作状态同步
4. 不要求一次性删掉所有旧字段
5. 不要求 `client` 立刻完全重写状态层

---

## 17. 最终结论

当前项目最核心的建模错误，不是某个枚举值不准确，而是：

`把本来属于 asset / draft / runtime / task / export 的状态，硬压成了 Project.workflow_state 这一个字段。`

推荐的重构方向是：

1. `Project` 退回容器元数据
2. `asset` 承担素材处理状态
3. `EditDraft` 只表达内容事实
4. `ProjectRuntimeState` 承担 `agent` 工作记忆
5. `Task` 承担运行过程
6. `Capabilities` 负责动作准入
7. `SummaryState` 只做展示摘要

这样才能同时满足：

1. 空项目先规划
2. 素材处理中仍可聊天
3. 部分素材就绪即可检索
4. `agent` 有稳定状态可读可写
5. `client` 不再依赖脆弱的单轴状态机猜测系统行为

一句话总结：

`EntroCut` 的项目状态管理，应从“单一 workflow 标签”升级成“按实体归属的事实层 + capability 派生层”。`
