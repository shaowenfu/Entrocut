# 项目状态管理重构任务文档

本文档面向负责 `Project State Management（项目状态管理）` 改造的工程师。

你的任务不是给当前 `workflow_state` 换一组枚举名，而是把 `core` 从“单一项目状态字段驱动”重构成“按实体归属的事实状态 + capability（能力）派生”的可维护形态。

设计依据以 [docs/store/04_project_state_management_refactor_design.md](/home/sherwen/MyProjects/Entrocut/docs/store/04_project_state_management_refactor_design.md) 为准。

---

## 执行状态（2026-03-31）

本文档对应的改造任务已经完成主要实现，当前应视为“历史任务文档 + 收尾参考”，而不是最新公开契约。

当前落地情况：

1. `Phase 1：Schema 与 SQLite 骨架升级`
   - 已完成
2. `Phase 2：Store 与 Repository 重构`
   - 已完成
3. `Phase 3：素材处理状态重构`
   - 已完成
4. `Phase 4：Chat / Agent / Context 重构`
   - 已完成
5. `兼容层收口`
   - 已完成公开 API、前端与事件层的切换

当前真实结果：

1. 公开 `Project` 模型已不再暴露 `workflow_state`
2. 公开 `WorkspaceSnapshot` 已以 `summary_state / media_summary / runtime_state / capabilities / active_tasks` 为核心
3. 前端已停止依赖 `project.workflow_state` 与 `task.updated.workflow_state`
4. `workflow_state` 只剩 `SQLite` 内部兼容持久化用途

剩余可选收尾：

1. 在确认不再需要旧库兼容后，删除 `SQLite workflow_state` 物理列
2. 进一步弱化 `active_task` 兼容字段的存在感

最新公开契约请以 [docs/store/01_core_api_ws_contract.md](/home/sherwen/MyProjects/Entrocut/docs/store/01_core_api_ws_contract.md) 为准。

---

## 1. Context

当前 `core` 的状态管理存在 4 个结构性问题：

1. `Project.workflow_state` 同时表达素材状态、`agent` 运行状态、导出状态和结果状态
2. `active_task` 默认一个项目同一时刻只能有一个重要过程
3. `queue_chat` 在无素材时直接拒绝请求，无法支持 `planning-only（纯规划）` 对话
4. `planner context` 只能读到粗粒度 `workflow_state`，读不到真正可决策的运行时事实

这与项目目标不一致。

根据 [README.md](/home/sherwen/MyProjects/Entrocut/README.md)、[EntroCut_algorithm.md](/home/sherwen/MyProjects/Entrocut/EntroCut_algorithm.md)、[EntroCut_architecture.md](/home/sherwen/MyProjects/Entrocut/EntroCut_architecture.md)：

1. 系统目标是 `Chat-to-Cut（对话到剪辑）`
2. `Core` 是本地权威状态层
3. 用户应能先澄清意图，再逐步进入素材驱动的 `select -> compose -> evaluate -> revise` 闭环

这直接推出：

1. 空项目必须合法
2. 无素材时 `chat` 必须可用
3. `retrieve` 等依赖素材索引的工具必须显式 gating（准入控制）
4. 状态必须按实体归属，而不是全部挂到 `Project`

---

## 2. 总体目标

本次改造完成后，系统应满足：

1. `create_project` 允许空项目创建
2. `Project` 退回容器元数据，不再承担权威流程状态
3. 素材处理状态归属到 `asset`
4. `ProjectRuntimeState` 成为 `agent` 的持久化工作状态层
5. `Task` 支持按 `slot` 并发，而不是只有一个 `active_task`
6. `ProjectCapabilities` 由事实派生，供 `client` 和 `planner` 读取
7. 旧 `workflow_state` 在兼容期内只作为 `summary_state` 的兼容输出，不再作为权威事实源

一句话：

`状态按事实分层，动作按 capability 准入，展示层只消费派生摘要。`

---

## 3. 明确 Non-goals

本任务明确不做：

1. 不把当前 `task` 系统升级成通用 `workflow engine（工作流引擎）`
2. 不在这一轮实现多人协作状态同步
3. 不在这一轮彻底重写 `client` 的全部 `store`
4. 不在这一轮补全所有复杂素材处理算法
5. 不要求一次性删除所有旧字段；允许存在兼容期

---

## 4. 推荐目标模型

### 4.1 核心资源

本轮要把状态拆成以下几类资源：

1. `ProjectModel`
   - 只保留容器元数据
2. `AssetProcessingState`
   - 每个 `asset` 的处理阶段与进度
3. `EditDraft`
   - 当前草案的内容事实
4. `ProjectRuntimeState`
   - `goal / focus / conversation / retrieval / execution`
5. `TaskModel`
   - 按 `slot` 表达异步过程
6. `ProjectCapabilities`
   - 由事实派生的动作可用性
7. `ProjectSummaryState`
   - 仅用于列表展示的单标签摘要

### 4.2 capability 目标

至少要支持：

1. `can_send_chat`
2. `chat_mode = planning_only | editing`
3. `can_retrieve`
4. `can_inspect`
5. `can_patch_draft`
6. `can_preview`
7. `can_export`
8. `blocking_reasons`

### 4.3 task slot 目标

至少定义：

1. `media`
2. `agent`
3. `export`

并明确并发规则：

1. 同一项目允许多个 `media` 任务
2. 同一项目同时只允许一个 `agent` 任务
3. 同一项目同时只允许一个 `export` 任务
4. `media` 与 `agent(planning-only)` 可以并存

---

## 5. 分阶段改造方案

不建议一个超大 PR 一次做完。推荐拆成 5 个阶段推进，每个阶段都能单独验证。

### Phase 0：契约冻结与兼容策略

目标：

1. 固定新旧状态并存期的读写规则
2. 避免前后端同时失稳

任务：

1. 以 [docs/store/04_project_state_management_refactor_design.md](/home/sherwen/MyProjects/Entrocut/docs/store/04_project_state_management_refactor_design.md) 为唯一设计基线
2. 明确 `workflow_state` 在兼容期的地位：
   - 只读、派生、`deprecated（弃用）`
3. 明确 `WorkspaceSnapshot` 的过渡策略：
   - 新增 `active_tasks`
   - 保留 `active_task` 兼容字段
4. 明确 `Project` 资源的过渡策略：
   - 先保留 `workflow_state`
   - 同时新增 `summary_state`、`capabilities`

交付标准：

1. 所有后续阶段都以“新增字段优先、旧字段兼容输出”为原则
2. 不出现“后端先删字段，前端立即崩”的破坏式改动

---

### Phase 1：Schema 与 SQLite 骨架升级

目标：

1. 先把状态模型和持久化表结构准备好
2. 不立即大改业务逻辑

必改文件：

1. [core/schemas.py](/home/sherwen/MyProjects/Entrocut/core/schemas.py)
2. [core/state.py](/home/sherwen/MyProjects/Entrocut/core/state.py)

任务：

1. 在 `schemas.py` 中新增以下模型或类型：
   - `ProjectLifecycleState`
   - `AssetProcessingStage`
   - `TaskSlot`
   - `ProjectSummaryState`
   - `ProjectCapabilities`
   - `ProjectMediaSummary`
   - `GoalState`
   - `FocusState`
   - `ConversationState`
   - `RetrievalState`
   - `ExecutionState`
   - `ProjectRuntimeState`
2. 收缩 `ProjectModel`：
   - 新增 `lifecycle_state`
   - 保留 `workflow_state` 兼容字段，但标记为过渡字段
3. 扩展 `TaskModel`：
   - 新增 `slot`
   - 新增 `owner_type`
   - 新增 `owner_id`
   - 新增 `result`
   - 新增 `error`
4. 扩展 `WorkspaceSnapshotModel`：
   - 新增 `media_summary`
   - 新增 `runtime_state`
   - 新增 `capabilities`
   - 新增 `active_tasks`
   - 暂时保留 `active_task`
5. 扩展 `state.py` 数据库结构：
   - `projects` 新增 `lifecycle_state`
   - `project_runtime` 新增 `runtime_state_json`
   - `project_runtime` 新增 `summary_state`
   - `tasks` 新增 `slot / owner_type / owner_id / result_json / error_json`
   - `assets` 新增 `processing_stage / processing_progress / clip_count / indexed_clip_count / last_error_json / updated_at`
6. 编写 additive migration（增量迁移）：
   - 老库自动补列
   - 老记录自动生成默认 `runtime_state_json`

交付标准：

1. 现有数据库可自动升级
2. 老项目仍能加载
3. 新模型可序列化/反序列化

风险点：

1. `sqlite3` 迁移时列不存在
2. 旧记录缺字段导致 `Pydantic` 校验失败

处理方式：

1. 所有新字段先提供合理默认值
2. 加载老记录时显式做 normalize（标准化）

---

### Phase 2：Store 与 Repository 重构

目标：

1. 让 `store` 不再围绕单一 `workflow_state + active_task` 组织逻辑
2. 建立事实状态到 capability 的统一派生路径

必改文件：

1. [core/store.py](/home/sherwen/MyProjects/Entrocut/core/store.py)
2. [core/helpers.py](/home/sherwen/MyProjects/Entrocut/core/helpers.py)
3. [core/state.py](/home/sherwen/MyProjects/Entrocut/core/state.py)

任务：

1. 新增默认状态构造函数：
   - `_default_project_runtime_state()`
   - `_default_project_capabilities()`
   - `_default_media_summary()`
2. 新增聚合/派生函数：
   - `_derive_media_summary(record)`
   - `_derive_project_capabilities(record)`
   - `_derive_summary_state(record)`
   - `_list_active_tasks(record)`
3. 重构 `create_project`：
   - 删除“至少存在 title/prompt/media 之一”的校验
   - 支持空项目创建
   - 无输入时标题默认 `Untitled Project`
   - 初始化空 `ProjectRuntimeState`
   - 初始化空 `ProjectMediaSummary`
4. 重构 `workspace_snapshot`：
   - 返回 `runtime_state`
   - 返回 `capabilities`
   - 返回 `media_summary`
   - 返回 `active_tasks`
   - 兼容性返回单一 `active_task`
5. 重构任务管理：
   - 用 `slot` 查重，而不是项目级全局互斥
   - 增加 `list_running_tasks(project_id, slot=None)`
   - 增加 `get_running_task(project_id, slot)`
6. 重构存储持久化：
   - `project_runtime` 同步写入 `runtime_state_json`
   - `tasks` 同步写入新增字段
   - `assets` 同步写入处理状态字段

交付标准：

1. 空项目创建成功
2. `WorkspaceSnapshot` 能完整返回新状态
3. `capabilities` 派生逻辑只有一处权威实现

---

### Phase 3：素材处理状态重构

目标：

1. 把素材处理事实下沉到 `asset`
2. 项目只消费聚合后的 `media_summary`

必改文件：

1. [core/store.py](/home/sherwen/MyProjects/Entrocut/core/store.py)
2. [core/state.py](/home/sherwen/MyProjects/Entrocut/core/state.py)
3. 如有必要，补充 [core/helpers.py](/home/sherwen/MyProjects/Entrocut/core/helpers.py)

任务：

1. 为每个新导入素材创建 `asset processing state`
2. 将素材处理过程改写为显式阶段：
   - `pending`
   - `segmenting`
   - `vectorizing`
   - `ready`
   - `failed`
3. 让 `queue_assets_import` 不再只改 `project.workflow_state`
4. 让 `_run_assets_import` 在每个阶段都更新：
   - `asset.processing_stage`
   - `asset.processing_progress`
   - `clip_count`
   - `indexed_clip_count`
5. 让 `ProjectMediaSummary.retrieval_ready` 表达：
   - 只要存在至少一批可检索 `clip` 即为 `True`
   - 不要求所有素材都处理完成
6. 输出新的事件：
   - `asset.updated`
   - `capabilities.updated`
   - `project.summary.updated`

交付标准：

1. 部分素材就绪即可进入 `editing`
2. 素材处理中仍能继续聊天
3. 前端能区分“完全无素材”和“素材处理中”

---

### Phase 4：Chat / Agent / Context 重构

目标：

1. 支持无素材时 `planning-only` 聊天
2. 让 `planner` 读取新状态而不是猜测 `workflow_state`

必改文件：

1. [core/store.py](/home/sherwen/MyProjects/Entrocut/core/store.py)
2. [core/context.py](/home/sherwen/MyProjects/Entrocut/core/context.py)
3. [core/agent.py](/home/sherwen/MyProjects/Entrocut/core/agent.py)
4. 如有必要，调整 [core/routers/projects.py](/home/sherwen/MyProjects/Entrocut/core/routers/projects.py)

任务：

1. 重构 `queue_chat`：
   - 删除 `MEDIA_REQUIRED_FOR_CHAT`
   - 只在 `agent` slot 已运行时拒绝
   - 启动聊天前先读取 `capabilities`
2. 定义 `chat_mode` 行为：
   - `planning_only`：允许澄清需求、记录目标、等待素材
   - `editing`：允许完整工具链
3. 将以下信息注入 `planner context`：
   - `media_summary`
   - `project_capabilities`
   - `runtime_state`
   - `summary_state`
4. 程序侧增加 tool gating：
   - `read` 永远允许
   - `retrieve` 仅在 `can_retrieve`
   - `inspect` 仅在存在候选池
   - `preview/export` 仅在 `can_preview / can_export`
5. 让 `ProjectRuntimeState` 真正回写：
   - `goal_state`
   - `focus_state`
   - `conversation_state`
   - `retrieval_state`
   - `execution_state`
6. 最小落地策略：
   - 不要求第一版就让模型完整维护所有子状态
   - 允许先用程序侧规则写入一部分关键字段

建议优先实现的最小状态回写：

1. `execution_state.agent_run_state`
2. `execution_state.current_task_id`
3. `conversation_state.pending_questions`
4. `retrieval_state.retrieval_ready`
5. `focus_state` 从 `target` 继承

交付标准：

1. 空项目可聊天
2. 无素材时 `planner` 不会误调用 `retrieve`
3. 有可检索素材时自动进入 `editing` 模式

---

### Phase 5：导出、WebSocket 与兼容层收口

目标：

1. 完成新旧状态的事件推送和 UI 兼容
2. 把 `workflow_state` 退化为兼容输出

必改文件：

1. [core/store.py](/home/sherwen/MyProjects/Entrocut/core/store.py)
2. [core/routers/system.py](/home/sherwen/MyProjects/Entrocut/core/routers/system.py)
3. [docs/store/01_core_api_ws_contract.md](/home/sherwen/MyProjects/Entrocut/docs/store/01_core_api_ws_contract.md)
4. 视范围而定，后续同步 `client` 读取逻辑

任务：

1. 导出流程改为：
   - 使用 `export` slot
   - 显式绑定目标 `draft version`
2. `EditDraft.status` 不再承载 `rendering`
3. 统一事件更新路径：
   - `task.updated`
   - `runtime_state.updated`
   - `capabilities.updated`
   - `asset.updated`
   - `project.summary.updated`
4. 为兼容前端旧逻辑：
   - 继续派生 `workflow_state`
   - 但只从 `summary_state` 映射
5. 更新文档契约：
   - `Project` 新字段
   - `WorkspaceSnapshot` 新字段
   - 事件 payload 新字段

交付标准：

1. 前端在兼容期内不需要一次性重写全部逻辑
2. 新客户端可以完全不依赖 `workflow_state`

---

## 6. 文件级改动清单

### 必改

1. [core/schemas.py](/home/sherwen/MyProjects/Entrocut/core/schemas.py)
2. [core/state.py](/home/sherwen/MyProjects/Entrocut/core/state.py)
3. [core/store.py](/home/sherwen/MyProjects/Entrocut/core/store.py)
4. [core/context.py](/home/sherwen/MyProjects/Entrocut/core/context.py)
5. [core/agent.py](/home/sherwen/MyProjects/Entrocut/core/agent.py)
6. [docs/store/01_core_api_ws_contract.md](/home/sherwen/MyProjects/Entrocut/docs/store/01_core_api_ws_contract.md)

### 大概率会改

1. [core/helpers.py](/home/sherwen/MyProjects/Entrocut/core/helpers.py)
2. [core/routers/projects.py](/home/sherwen/MyProjects/Entrocut/core/routers/projects.py)
3. [core/routers/system.py](/home/sherwen/MyProjects/Entrocut/core/routers/system.py)
4. [core/README.md](/home/sherwen/MyProjects/Entrocut/core/README.md)

### 测试必改

1. [core/tests/test_server_toolchain_integration.py](/home/sherwen/MyProjects/Entrocut/core/tests/test_server_toolchain_integration.py)
2. [core/tests/test_context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/tests/test_context_engineering.py)

### 后续 `client` 跟进项

1. 读取 `workspace.capabilities`
2. 读取 `workspace.runtime_state`
3. 读取 `workspace.media_summary`
4. 读取 `workspace.active_tasks`
5. 停止依赖 `project.workflow_state` 做准入判断

---

## 7. 推荐 PR 切分

不建议一个 PR 做完全部改动。推荐拆成 3 个连续 PR。

### PR 1：Schema / SQLite / Snapshot 骨架

包含：

1. `schemas.py`
2. `state.py`
3. `store.py` 中默认状态与 snapshot 返回
4. 空项目创建

不包含：

1. 完整 `agent` 重构
2. 前端迁移

目标：

1. 先让“新状态模型能存在并被持久化”

### PR 2：Asset / Task / Chat capability

包含：

1. `asset processing state`
2. `task slot`
3. `queue_chat` 支持 `planning_only`
4. `capabilities` 派生

目标：

1. 先让后端行为正确

### PR 3：Agent / Context / WS / Cleanup

包含：

1. `planner context` 切到新状态
2. tool gating
3. 新事件推送
4. 文档契约更新
5. 兼容字段收口

目标：

1. 让 `agent` 真正基于新状态模型运行

---

## 8. 测试与验证矩阵

### 8.1 `create_project`

必须覆盖：

1. 空请求可创建项目
2. 默认标题正确
3. 初始 `chat_mode == planning_only`
4. 初始 `can_send_chat == True`
5. 初始 `can_retrieve == False`

### 8.2 素材导入

必须覆盖：

1. 导入后出现 `media` task
2. `asset.processing_stage` 按阶段推进
3. `media_summary` 正确聚合
4. 部分素材就绪时 `can_retrieve == True`

### 8.3 聊天

必须覆盖：

1. 无素材时允许聊天
2. 无素材时 `retrieve` 被程序侧拒绝
3. 有素材但未索引完成时仍是 `planning_only`
4. 有可检索素材时进入 `editing`
5. 同时存在 `media` task 时仍允许 `agent` 任务启动

### 8.4 导出

必须覆盖：

1. 无 `shots` 不允许导出
2. 有 `shots` 时允许导出
3. 导出使用 `export` slot
4. 导出完成后不污染 `EditDraft` 的内容事实状态

### 8.5 兼容层

必须覆盖：

1. 老库可加载
2. 旧 `workflow_state` 仍能派生输出
3. `active_task` 在兼容期内仍可返回

---

## 9. 风险与注意事项

### 9.1 最大风险：同时改“建模 + 持久化 + 行为”

这是一个多层联动改造。

不要在一个提交里同时：

1. 改数据库
2. 改 `store`
3. 改 `agent`
4. 改前端

否则定位回归会非常困难。

### 9.2 不要把 capability 逻辑散落多处

`can_retrieve / can_export / chat_mode` 必须只有一个派生入口。

禁止：

1. `store.py` 一套判断
2. `context.py` 一套判断
3. `router` 再写一套判断

### 9.3 不要把 runtime state 设计成数据库镜像

`ProjectRuntimeState` 的目标是让下一步决策更稳定，不是把所有字段都再复制一份。

只保留后续决策真的依赖的事实。

### 9.4 不要急着删旧字段

兼容期策略必须明确：

1. 先新增
2. 再迁移读取方
3. 最后删除旧字段

---

## 10. 最终验收标准

这轮改造合格的标准不是“状态名字更优雅”，而是：

1. 用户可以创建空项目并开始 `planning-only chat`
2. 项目状态不再依赖单一 `workflow_state` 驱动核心逻辑
3. 素材、运行时、导出、草案状态已经按实体归属拆开
4. `planner` 能读到 `runtime_state + capabilities + media_summary`
5. `retrieve` 等工具由 capability 显式 gating
6. `task slot` 能表达基础并发事实
7. 兼容期内现有前端不会被破坏

一句话：

`你要把当前状态管理从“流程标签驱动”改造成“事实状态驱动”。`
