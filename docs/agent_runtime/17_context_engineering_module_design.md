# Context Engineering Module Design

本文档只讨论当前已经落地到代码里的 `core/context_engineering.py`。

目标不是描述最终成熟形态，而是固定这次重构做对了什么、暂时故意没做什么，以及未来应该如何演进。

---

## 1. 为什么要把上下文编排独立成模块

在重构之前，`core/server.py` 里的上下文编排是：

1. 一边读取运行时数据
2. 一边做字段裁剪
3. 一边拼 `planner` 输入
4. 一边内嵌 `system prompt`

这种写法短期能跑，但有两个根本问题：

1. `server.py` 同时承担 `API / schema / state store / task orchestration / context assembly`
2. 上下文工程会退化成“临时变量拼接”，而不是“从 runtime state 裁剪 decision context”

所以这次拆模块的目标很克制：

`先把“上下文原材料 -> 上下文成品”的生产链条独立出来。`

---

## 2. 当前模块的职责边界

`core/context_engineering.py` 当前只负责两件事：

1. 从调用方给出的原材料构建 `PlannerRuntimeState`
2. 从 `PlannerRuntimeState` 派生 `planner_input`

它当前明确不负责：

1. 访问数据库或全局 store
2. 调用模型
3. 执行工具
4. 决定 loop 是否继续
5. 持久化 `memory / scope / goal`

这很重要。

当前模块不是 `agent runtime` 本身，而是：

`planner context factory（规划器上下文工厂）`

---

## 3. 当前模块结构

当前代码主要分为三层。

### 3.1 运行时状态模型

1. `PlannerRuntimeState`
2. `PlannerContextPacket`

作用：

1. 把上下文工程从“散 dict”收口成显式结构
2. 区分“完整 runtime state”和“给 planner 的输入”

### 3.2 分块构建函数

当前已经拆出：

1. `build_agent_identity_state`
2. `build_goal_state`
3. `build_scope_state`
4. `build_draft_state`
5. `build_tool_capability_state`
6. `build_working_memory_state`
7. `build_runtime_capabilities_state`
8. `build_trace_state`

作用：

1. 每个函数只负责一个上下文分块
2. 未来可以单独替换，不必重写总流程

### 3.3 总装函数

1. `build_planner_context_packet`
2. `build_planner_system_prompt`

作用：

1. 统一把分块状态装配成 `planner_input`
2. 把 `system prompt` 从 `server.py` 中剥离出来

---

## 4. 为什么当前设计是对的

按第一性原理，这次重构真正解决的不是“代码风格”，而是分清了三层东西：

1. `raw materials（原材料）`
   - `record`
   - `prompt`
   - `target`
   - `draft_summary`
   - `chat_history_summary`
   - `tool_observations`

2. `runtime state（运行时状态）`
   - `identity`
   - `goal`
   - `scope`
   - `draft`
   - `tools`
   - `memory`
   - `runtime_capabilities`
   - `trace`

3. `planner input（决策输入）`
   - 真正给模型看的裁剪结果

只要这三层不分开，后面任何“上下文优化”都只是局部 prompt patch。

---

## 5. 当前为什么保留大量 TODO

这次模块化重构刻意没有把所有语义逻辑一口气做完，而是保留了显式 `TODO`。

原因不是偷懒，而是控制风险。

当前最需要先固定的是框架，不是细节。

如果在这一步就把这些逻辑一次性塞进去：

1. `soul.md` 身份注入
2. `goal` 结构化提炼
3. `scope` 持久化更新
4. `tool registry` 摘要
5. `working memory` 压缩
6. 正式 `system prompt`

那就很容易重新回到“大函数里继续堆逻辑”的旧路。

所以这次故意先把这些内容固定成独立占位：

1. 先把边界挖出来
2. 再逐块填语义

这是更稳的推进方式。

---

## 6. 当前模块与 server.py 的关系

现在的关系应理解成：

1. `server.py`
   - 提供上下文原材料
   - 发起 planner 调用
   - 处理 loop 控制流

2. `context_engineering.py`
   - 负责把原材料装成 `planner_input`

所以 `server.py` 现在已经不应该再知道：

1. `identity` 细节怎么生成
2. `goal` 细节怎么提炼
3. `tool` 能力描述怎么组织
4. `memory` 该怎么压缩

这正是模块抽离后的价值。

---

## 7. 未来演进顺序

如果继续沿当前方向推进，建议顺序如下。

### 7.1 第一阶段：把 TODO 变成正式结构

优先填这三块：

1. `goal`
2. `scope`
3. `memory`

因为这三块直接决定 planner 每轮到底在看什么。

### 7.2 第二阶段：引入稳定 identity

把 `agent identity` 从硬编码占位升级成外部稳定来源，例如：

1. `soul.md`
2. 固定 schema 化配置

### 7.3 第三阶段：接入 tool registry

把当前静态工具列表升级成真正的能力摘要来源。

目标不是暴露实现细节，而是告诉 planner：

1. 能做什么
2. 什么时候该用
3. 什么情况下不该用

### 7.4 第四阶段：把 memory 从文本摘要升级成结构化 working memory

当前 `chat_history_summary` 还是弱结构。

后续应该逐步替换成：

1. `recent_decisions`
2. `recent_observations`
3. `pending_risks`
4. `open_questions`

### 7.5 第五阶段：让 scope 成为持久化 runtime state

当前 `scope` 只是请求态推断。

后续应该进入正式 runtime state，并支持：

1. 默认继承
2. 基于 observation 收缩
3. 在用户显式改焦点时重置

---

## 8. 当前明确不做的事

为了避免概念膨胀，这个模块当前明确不做：

1. 不做通用 prompt 模板系统
2. 不做复杂 context ranking
3. 不做多 agent context broker
4. 不做长期记忆存储
5. 不做跨文件配置驱动的所有逻辑

一句话：

`当前模块的目标不是把上下文工程做满，而是把它从 server.py 里解耦出来，变成一个可以稳定继续演进的独立层。`

---

## 9. 一句话结论

`core/context_engineering.py` 这次重构最重要的价值，不是“多了一个文件”，而是：

`项目第一次把上下文工程明确建模成了一个独立的运行时层。`

从现在开始，后续的上下文优化应该优先发生在这个模块里，而不是重新回到 `server.py` 里继续堆字符串。
