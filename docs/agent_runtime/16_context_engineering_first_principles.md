# Context Engineering First Principles

本文档不讨论“prompt 技巧”。

它只回答当前项目里一个更底层的问题：

`planner 在每一轮真正需要看到哪些信息，这些信息从哪里来，怎么被读取、更新和裁剪。`

如果这个问题不先固定，后续所有 `planner prompt`、`memory`、`agent loop` 都只会退化成临时拼接。

---

## 1. 第一性原理

对当前项目来说，上下文工程的目标不是“把尽可能多的信息塞进模型”，而是：

`把当前一步决策真正需要的最小高信号事实送进 planner。`

这意味着必须先区分两层：

1. `world state（世界事实）`
   - 系统当前知道什么
2. `decision context（决策上下文）`
   - 本轮 planner 实际看到什么

上下文不是原材料本身，而是从原材料里裁出来的一份决策输入。

---

## 2. 当前项目里最深层不会变的事实

视频剪辑的本质不是“操作时间线”，而是：

`从候选片段集合里，围绕用户 intent 持续做 select -> compose -> evaluate -> revise，直到形成可执行的 EditDraft。`

所以 planner 无论如何演化，最底层都必须回答这 5 个问题：

1. 我们想做什么
2. 我们手里有什么
3. 我们当前做到哪一步了
4. 我们还能做什么
5. 下一步最值得做什么

从这里往上推，当前项目真正必要的信息只有 6 类：

1. `identity`
2. `goal`
3. `focus`
4. `draft`
5. `tools`
6. `memory`

---

## 3. 上下文原材料来自哪里

按当前仓库现状，原材料主要来自 6 个位置。

### 3.1 `record`

存储位置：

1. [core/server.py](/home/sherwen/MyProjects/Entrocut/core/server.py) 中 `InMemoryProjectStore._projects`

当前数据变量：

1. `record["project"]`
2. `record["edit_draft"]`
3. `record["chat_turns"]`
4. `record["active_task"]`
5. `record["export_result"]`
6. `record["sequence"]`

读取方式：

1. `store.get_project_or_raise(project_id)`
2. `store.workspace_snapshot(project_id)`

更新方式：

1. `create_project`
2. `queue_assets_import / _run_assets_import`
3. `queue_chat / _run_chat`
4. `queue_export / _run_export`

这是当前系统最主要的 `world state`

### 3.2 `auth_session_store`

存储位置：

1. [core/server.py](/home/sherwen/MyProjects/Entrocut/core/server.py) 中 `CoreAuthSessionStore`

当前数据变量：

1. `access_token`
2. `user_id`

读取方式：

1. `await auth_session_store.snapshot()`

更新方式：

1. `set_auth_session`
2. `clear_auth_session`

它不属于剪辑语义上下文，但属于执行上下文。

### 3.3 `/chat` 请求输入

来源：

1. `POST /api/v1/projects/{project_id}/chat`

当前数据变量：

1. `payload.prompt`
2. `payload.target`

这部分定义了本轮会话入口。

### 3.4 `target`

当前存储位置：

1. `ChatRequest.target`
2. `_run_chat(...)`
3. `_run_chat_agent_loop(...)`

当前问题：

1. 它还只是请求参数
2. 还没有升级成持久化 `focus state`

### 3.5 `planner context`

生成位置：

1. `_build_planner_messages(...)`

当前字段：

1. `project_id`
2. `iteration`
3. `user_input`
4. `target`
5. `workspace_snapshot`
6. `chat_history_summary`
7. `tool_observations`
8. `prototype_constraints`

这是 `decision context` 的现有雏形。

### 3.6 `tool observations`

当前存储位置：

1. 仅存在于 `_run_chat_agent_loop(...)` 的局部变量

当前问题：

1. 没有持久化
2. 没有稳定 schema
3. 没有进入正式 `working memory`

---

## 4. 当前项目真正必要的信息

从奥卡姆剃刀出发，当前项目不需要一个巨大的上下文分类表。

只需要 6 块。

### 4.1 `identity`

内容：

1. agent 是谁
2. 负责什么
3. 不负责什么
4. 允许怎样决策

来源：

1. 固定 `system instruction`
2. 未来建议落盘成 `soul.md`

### 4.2 `goal`

内容：

1. 当前用户想做什么
2. 当前成功条件是什么
3. 当前仍然缺什么信息

当前来源：

1. `payload.prompt`

未来建议：

1. 从原始 prompt 解析成显式 `goal_state`

### 4.3 `focus`

内容：

1. 当前工作焦点在哪
2. 是 `project-level`、`scene-level` 还是 `shot-level`

当前来源：

1. `payload.target`

未来建议：

1. 升级成持久化 `focus_state`
2. 默认跨 loop 继承
3. 只有在证据充分时更新

### 4.4 `draft`

内容：

1. 当前 `EditDraft`
2. 当前素材与候选片段空间

当前来源：

1. `record["edit_draft"]`

当前原则：

1. 给 planner 的不应该是全量 draft
2. 而应该是当前一步所需的 `working draft summary`

### 4.5 `tools`

内容：

1. 当前有哪些工具
2. 每个工具解决什么问题
3. 输入输出边界是什么
4. 什么情况下不该使用

当前来源：

1. prompt 内硬编码

未来建议：

1. 从固定 `tool registry` 生成摘要注入

### 4.6 `memory`

内容：

1. 最近决策摘要
2. 最近工具观测
3. 当前未解决问题

当前来源：

1. `record["chat_turns"]`
2. loop 内 `observations`

未来建议：

1. 变成结构化 `working_memory_state`

---

## 5. `/chat` 级别和 `loop` 级别的区别

这两层不能混。

### 5.1 `/chat` 级别上下文

回答的是：

`这次会话启动时，系统整体知道什么？`

最小应包含：

1. `identity`
2. `user_input`
3. `goal`
4. `focus`
5. `draft summary`
6. `available tools`

### 5.2 `loop` 级别上下文

回答的是：

`当前第 N 轮时，planner 这一步真正需要看什么？`

它比 `/chat` 级别多出：

1. `recent observations`
2. `current_draft` 的循环内更新版本
3. 当前轮预算与停止条件

结论：

1. `/chat context` 是启动包
2. `loop context` 是每轮决策包

---

## 6. 当前字段的取舍判断

### 6.1 `project_id`

对程序路由有用，对模型决策通常不重要。

结论：

1. 可保留在 trace 层
2. 不应作为核心语义上下文

### 6.2 `iteration`

对程序控制必要，对模型只是辅助信号。

结论：

1. 可以给 planner
2. 但优先级低于 `goal / focus / draft / tools / memory`

### 6.3 `target`

这是核心字段。

没有它，planner 不知道当前该改哪里。

结论：

1. 必须保留
2. 未来必须升级成正式 `focus state`

### 6.4 `workspace_snapshot`

有必要，但不能是“全量工作区倾倒”。

结论：

1. 要保留
2. 但必须收缩成 `working_state_summary`

### 6.5 `tool_observations`

第一轮为空是正常现象。

结论：

1. 空列表不是问题
2. 后续轮次只保留最近少量高价值 observation

### 6.6 `prototype_constraints`

本质是当前 runtime guardrail。

结论：

1. 有必要
2. 后续建议重命名为 `runtime_capabilities` 或 `execution_constraints`

---

## 7. 推荐的最小 runtime state

按当前项目现状，建议未来把正式运行时状态固定成：

```ts
interface EditingRuntimeState {
  identity: AgentIdentityState;
  goal: GoalState;
  focus: FocusState;
  draft: DraftState;
  tools: ToolCapabilityState;
  memory: WorkingMemoryState;
}
```

其中最重要的不是类型名，而是这 6 个概念本身。

### 7.1 `AgentIdentityState`

至少包括：

1. `agent_name`
2. `role`
3. `core_principles`
4. `non_goals`

### 7.2 `GoalState`

至少包括：

1. `user_intent`
2. `success_criteria`
3. `open_questions`

### 7.3 `FocusState`

至少包括：

1. `scope_type`
2. `scene_id`
3. `shot_id`
4. `selection_reason`

### 7.4 `DraftState`

至少包括：

1. `edit_draft`
2. `draft_summary`
3. `candidate_space_summary`

### 7.5 `ToolCapabilityState`

至少包括：

1. `available_tools`
2. `tool_constraints`

### 7.6 `WorkingMemoryState`

至少包括：

1. `recent_decisions`
2. `recent_observations`
3. `pending_risks`

---

## 8. 规划到当前代码的最小落点

如果继续沿当前代码推进，而不是立刻大拆重构，建议顺序如下：

1. 在 `planner context` 中显式加入 `agent_identity`
2. 把原始 `prompt` 升级成结构化 `goal summary`
3. 把 `target` 从请求参数升级成 `focus state`
4. 把 `workspace_snapshot` 改名并收缩为 `working_state_summary`
5. 把 `tool_observations` 结构化并纳入 `working memory`
6. 把 `prototype_constraints` 重命名为 `runtime_capabilities`

做到这一步，当前项目的上下文工程才算从“临时拼接变量”升级成“从 runtime state 裁剪 decision context”。

---

## 9. 一句话结论

当前项目里，上下文工程最核心的工作不是写更花的 prompt，而是先把这些边界固定下来：

1. 哪些是原材料
2. 哪些是运行时状态
3. 哪些是本轮决策真正需要看到的最小事实

只有这样，`planner` 才是在“基于状态做决策”，而不是“基于字符串做猜测”。
