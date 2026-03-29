# Context Engineering PR 任务文档

本文档面向负责 `Context Engineering（上下文工程）` 的工程师。

你的任务不是调 prompt 小技巧，而是把当前 `core` 的上下文编排从“临时变量拼装”推进到“从 runtime state 裁剪 decision context”的正式结构。

你会和另一位负责 `Agent Loop（执行闭环）` 的工程师并行工作。

两个 PR 不要求严格互斥，但要方便合并。

你的主责非常明确：

`你负责决策输入，不负责主导工具执行闭环。`

如果你需要触碰少量 loop 接口来完成接线，这是允许的；但不要把 PR 演变成对工具执行与状态回写逻辑的全面重写。

---

## 1. 开发目标

你要完成的是：

1. 把当前 [context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/context_engineering.py) 里的 `TODO` 占位逐步替换成正式结构
2. 固定当前项目的最小 `runtime state`
3. 让 `/chat` 级别上下文和 `loop` 级别上下文真正分层
4. 让 planner 看到的是“当前一步决策真正需要的最小高信号上下文”，而不是一大堆散乱字段
5. 保持当前 `core` 外部 API 稳定，并尽量降低和 `Agent Loop` PR 的冲突

这里的“生成级需求”指的是：

1. 上下文来源清晰
2. 裁剪规则可解释
3. 结构可测试
4. 后续可继续演进
5. 不把逻辑重新塞回 `server.py`

---

## 2. 你负责的主边界

你应主导这些部分：

1. `PlannerRuntimeState` 的正式结构
2. `identity / goal / scope / draft / tools / memory / runtime_capabilities` 的构建逻辑
3. `planner_input` 的字段裁剪策略
4. `system prompt` 的稳定来源和组织方式
5. `/chat context` 和 `loop context` 的边界
6. 上下文工程相关单元测试

你可以少量触碰这些部分，但不要主导其整体设计：

1. `server.py` 中 `_build_planner_messages(...)` 的接线
2. `_run_chat_agent_loop(...)` 为传递 observation/scope 新增的少量字段

你不应主导这些部分：

1. 工具执行调度
2. loop 内状态写回
3. 继续/停止控制流

---

## 3. 当前现状

当前 `main` 已经具备这些基础：

1. `context_engineering.py` 已存在
2. 已有显式结构：
   - `PlannerRuntimeState`
   - `PlannerContextPacket`
3. 已有分块构建函数：
   - `build_agent_identity_state`
   - `build_goal_state`
   - `build_scope_state`
   - `build_draft_state`
   - `build_tool_capability_state`
   - `build_working_memory_state`
   - `build_runtime_capabilities_state`
   - `build_trace_state`
4. `server.py` 已通过该模块生成 `planner_input`

也就是说，你现在不是在“提新想法”，而是在已有模块化框架上把它做成正式可用层。

---

## 4. 推荐开发方向

### 4.1 先把 6 块最小 runtime state 固定下来

建议优先围绕这 6 块推进：

1. `identity`
2. `goal`
3. `scope`
4. `draft`
5. `tools`
6. `memory`

不要在这一轮继续扩展更多抽象层。

### 4.2 先区分“原材料”和“决策输入”

你的设计必须明确分开：

1. `raw materials`
   - `record`
   - `prompt`
   - `target`
   - `chat_turns`
   - `tool_observations`
2. `runtime state`
3. `planner_input`

只要这三层不分开，后面就还会退化回 prompt 拼装。

### 4.3 `goal` 需要正式结构化

当前最大缺口之一是：

1. 只有原始 `prompt`
2. 没有正式 `goal state`

这一轮至少应收口出：

1. `user_intent`
2. `goal_summary`
3. `success_criteria`
4. `open_questions`

允许最初实现偏启发式，但结构必须先固定。

### 4.4 `scope` 不是伪需求，但不要误做成“强制局部编辑”

建议把它理解成：

`current working scope（当前工作范围）`

而不是“用户必须先指定的局部位置”。

最小上应支持：

1. `project-level`
2. `scene-level`
3. `shot-level`

当前可以先由：

1. `ChatRequest.target`
2. `EditDraft.selected_scene_id`
3. `EditDraft.selected_shot_id`

做启发式推导。

### 4.5 `tools` 必须以正式高层工具集合注入

当前最小工具集合是：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

请以 [05_tool_layer_minimal_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/05_tool_layer_minimal_contract.md) 为准。

不要漏掉 `read`。

工具层注入内容至少应包含：

1. 工具名
2. 作用
3. 何时适用
4. 何时不该用

### 4.6 `memory` 不能只是聊天文本堆叠

当前你不一定要一次性做出完整长期记忆，但至少应推动 `working memory` 正式化。

建议优先结构化为：

1. `recent_chat_summary`
2. `recent_decisions`
3. `recent_tool_observations`
4. `pending_risks`
5. `open_questions`

### 4.7 `system prompt` 必须有稳定来源

当前占位里已经明确提到：

1. `soul.md-backed planner instructions`
2. `tool usage policy`
3. `context compaction policy`

这一轮建议至少做到：

1. 逻辑位置固定
2. 字段来源清楚
3. 文本结构稳定

哪怕部分内容仍需占位，也不要再回到 `server.py` 里写长字符串。

---

## 5. 必读文档清单

你至少要按这个顺序阅读：

1. [README.md](/home/sherwen/MyProjects/Entrocut/README.md)
2. [core/README.md](/home/sherwen/MyProjects/Entrocut/core/README.md)
3. [11_memory_context_layer_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/11_memory_context_layer_design.md)
4. [12_action_context_packet_schema.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/12_action_context_packet_schema.md)
5. [13_context_assembler_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/13_context_assembler_design.md)
6. [15_execution_loop_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/15_execution_loop_design.md)
7. [16_context_engineering_first_principles.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/16_context_engineering_first_principles.md)
8. [17_context_engineering_module_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/17_context_engineering_module_design.md)
9. [05_tool_layer_minimal_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/05_tool_layer_minimal_contract.md)

代码入口优先看：

1. [context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/context_engineering.py)
2. [server.py](/home/sherwen/MyProjects/Entrocut/core/server.py)
3. [test_server_toolchain_integration.py](/home/sherwen/MyProjects/Entrocut/core/tests/test_server_toolchain_integration.py)

---

## 6. 单元测试要求

你的 PR 必须补齐能够证明上下文工程已从“散变量拼装”升级为“结构化裁剪”的测试。

最低要求：

1. `PlannerRuntimeState` 构建测试
2. `goal` 提炼测试
3. `scope` 推导测试
4. `tools` 注入测试，明确包含 `read`
5. `memory` 构建测试
6. `planner_input` 裁剪测试
7. 至少一个和 `server.py` 接线的集成式测试

建议测试覆盖：

1. 用户只给全局目标时，`scope` 默认到 `project-level`
2. 用户显式指定 `scene/shot target` 时，`scope` 正确收敛
3. 第一轮没有 `tool_observations` 时，context 仍合法
4. 有最近 observation 时，planner_input 能正确接入
5. `system prompt` 生成函数能稳定输出所需结构

测试不应只看字段“存在”。

应尽量验证：

1. 字段是否来自正确原材料
2. 低价值字段没有占据主干
3. 高价值字段确实进入 planner_input

---

## 7. 合并友好要求

因为另一位工程师会同时推进 `Agent Loop`，请遵守：

1. 不要重写 `_run_chat_agent_loop(...)` 的整体控制流
2. 如需新增字段，优先增量式追加，不做大规模字段更名
3. 尽量把语义建模限制在 `context_engineering.py` 附近
4. 如需修改 `server.py`，优先改接线而不是改业务流程
5. 保持当前 `PlannerDecisionModel` 外部契约稳定，除非有非常强的理由

---

## 8. 最终交付标准

PR 合格的最低标准不是“prompt 更复杂了”，而是：

1. 当前项目的上下文原材料、runtime state、planner_input 三层边界已经清晰
2. `goal / scope / tools / memory` 形成正式结构
3. `read / retrieve / inspect / patch / preview` 五类工具都在上下文里有清晰定位
4. 测试能证明 context 是被正确构建和裁剪的
5. 代码结构不会阻碍另一位工程师的 loop PR 合并

一句话：

`你要把当前的上下文工程从“拼字符串”推进到“状态驱动的决策输入层”。`
