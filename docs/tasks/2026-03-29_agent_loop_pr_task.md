# Agent Loop PR 任务文档

本文档面向负责 `Agent Loop（执行闭环）` 的工程师。

你的任务不是做一个抽象框架，而是基于当前 `main`，把 `core/chat` 从“能调 planner 的循环骨架”推进到“真正能执行一步工具、观测结果、回写状态、再规划”的最小生产可用形态。

你会和另一位负责 `Context Engineering（上下文工程）` 的工程师并行工作。

两个 PR 不要求严格互斥，但要方便合并。

你的主责非常明确：

`你负责执行闭环，不负责主导上下文模型设计。`

如果你需要触碰少量上下文接口来接线，这是允许的；但不要把 PR 演变成对 `context_engineering` 的全面重写。

---

## 1. 开发目标

你要完成的是：

1. 让 `_run_chat_agent_loop` 真正具备 `plan -> act -> observe -> write-back -> replan` 的最小闭环能力
2. 把当前函数外部的 `TODO` 占位替换成正式执行路径
3. 在当前项目收口好的高层工具边界上落地最小工具调度，而不是把底层媒体能力直接暴露给 planner
4. 保持当前 `core` 的外部 API 不被破坏
5. 让最终 PR 达到“生成级需求”，而不是“研究型 demo”

这里的“生成级需求”指的是：

1. 失败语义清晰
2. 关键路径有测试
3. 控制流可维护
4. 与当前文档方向一致
5. 不把当前仓库拉回大函数堆逻辑的旧路

---

## 2. 你负责的主边界

你应主导这些部分：

1. `_run_chat_agent_loop` 的真实控制流
2. `PlannerDecisionModel` 到工具执行之间的校验与路由
3. `ToolObservation` 的标准化
4. loop 内 `draft/state` 回写策略
5. 继续/停止条件
6. 失败处理与错误语义
7. loop 相关单元测试

你可以少量触碰这些部分，但不要主导其整体设计：

1. `context_engineering.py` 的输入字段接线
2. planner 输入中为 loop 增加的 observation / tool capability 字段

你不应主导这些部分：

1. `goal / scope / memory` 的完整上下文建模
2. `soul.md` 身份注入体系
3. `tool registry` 的长期设计

---

## 3. 当前现状

当前 `main` 已经具备这些基础：

1. `_run_chat_agent_loop` 已经有多轮循环外壳
2. 已新增函数外部 `TODO` 边界：
   - `_validate_planner_decision(...)`
   - `_should_continue_agent_loop(...)`
   - `_execute_tool_call_todo(...)`
   - `_apply_tool_observation_to_draft_todo(...)`
3. `planner context` 已经能够接收 `tool_observations`
4. `server.py` 中上下文编排已抽到 [context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/context_engineering.py)

也就是说，你现在不是从零开始，而是在已有骨架上把执行层真正补起来。

---

## 4. 推荐开发方向

### 4.1 先把 loop 的状态模型补齐

最低建议引入：

1. `ToolCallModel`
2. `ToolObservationModel`
3. `AgentLoopResultModel`

不要一开始就做成巨大通用框架。

你的任务是先让当前 `core/chat` 可闭环，不是先做平台化。

### 4.2 工具执行必须走高层语义边界

当前最小工具集合不是 4 个，而是 5 个：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

请以 [05_tool_layer_minimal_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/05_tool_layer_minimal_contract.md) 为准。

你在 loop 里执行的也必须是这 5 类高层工具，不要把底层 `ffmpeg`、向量检索细节或模型调用细节直接暴露给 planner。

### 4.3 推荐执行路径

建议最小落地顺序：

1. 把 `requires_tool` 从“直接抛 TODO”改成“进入正式工具路由”
2. 先实现统一工具调度层
3. 先支持 `read / patch` 这种本地确定性最强的路径
4. 再接 `retrieve / inspect / preview`
5. 每个工具执行后统一生成 `ToolObservation`
6. 每轮只允许一个明确动作
7. 下一轮必须基于新状态重规划

### 4.4 回写原则

loop 内回写不要走散乱字段更新。

应固定为：

1. 工具返回 `observation`
2. `observation` 提供 `state_delta`
3. loop 统一把 `state_delta` 映射成新的 `current_draft` / `memory` / `scope`

即使当前只先实现 `draft` 回写，也要保留这个结构。

### 4.5 错误语义要求

不要吞错，不要返回模糊失败。

建议至少覆盖：

1. `PLANNER_DECISION_INVALID`
2. `TOOL_NAME_NOT_SUPPORTED`
3. `TOOL_INPUT_INVALID`
4. `TOOL_EXECUTION_FAILED`
5. `TOOL_OBSERVATION_INVALID`
6. `STATE_WRITEBACK_FAILED`
7. `AGENT_LOOP_DID_NOT_FINALIZE`

---

## 5. 必读文档清单

你至少要按这个顺序阅读：

1. [README.md](/home/sherwen/MyProjects/Entrocut/README.md)
2. [core/README.md](/home/sherwen/MyProjects/Entrocut/core/README.md)
3. [05_tool_layer_minimal_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/05_tool_layer_minimal_contract.md)
4. [07a_retrieve_execution_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/07a_retrieve_execution_design.md)
5. [08b_inspect_execution_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/08b_inspect_execution_design.md)
6. [09_edit_draft_patch_schema.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/09_edit_draft_patch_schema.md)
7. [10_preview_tool_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/10_preview_tool_contract.md)
8. [15_execution_loop_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/15_execution_loop_design.md)
9. [16_context_engineering_first_principles.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/16_context_engineering_first_principles.md)
10. [17_context_engineering_module_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/17_context_engineering_module_design.md)

代码入口优先看：

1. [server.py](/home/sherwen/MyProjects/Entrocut/core/server.py)
2. [context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/context_engineering.py)
3. [test_server_toolchain_integration.py](/home/sherwen/MyProjects/Entrocut/core/tests/test_server_toolchain_integration.py)

---

## 6. 单元测试要求

你的 PR 必须补齐或新增能够证明闭环行为的单元测试。

最低要求：

1. `final decision` 路径继续通过
2. `requires_tool` 不再只是 `TODO` 报错
3. 至少一个工具执行成功后，loop 能进入下一轮重新规划
4. 至少一个工具执行失败时，错误语义清晰且任务收尾正确
5. 至少一个 `state write-back` 成功场景
6. 至少一个最大轮次耗尽场景

建议的测试粒度：

1. `unit tests`
   - 决策校验
   - 工具路由
   - observation 规范化
   - draft 回写
2. `integration-style tests`
   - `POST /chat` 启动 loop
   - mock planner 返回多轮决策
   - mock tool 执行结果
   - 校验最终 `workspace/edit_draft/chat_turns/task` 状态

测试不应只断言“HTTP 200”。

应断言：

1. 状态真的变化了
2. 轮次真的推进了
3. 错误真的可分支处理

---

## 7. 合并友好要求

因为另一位工程师会同时推进 `Context Engineering`，请遵守：

1. 不要重写 `context_engineering.py` 的整体结构
2. 如需新增字段，优先增量式追加，不做大改名
3. 尽量把 loop 逻辑的新增模型和辅助函数放在执行层邻近位置
4. 保持 `server.py` 外部 API 稳定
5. 在必要处写简短注释，说明为什么这样做，而不是描述显而易见的代码动作

---

## 8. 最终交付标准

PR 合格的最低标准不是“看起来更合理”，而是：

1. 当前 `core/chat` 已经具备最小真实闭环
2. 高层工具边界清楚
3. 测试能证明闭环确实在推进
4. 错误语义能支撑后续继续迭代
5. 代码结构不会阻碍另一位工程师的上下文工程 PR 合并

一句话：

`你要把当前的 agent loop 从“会计划”推进到“会执行并继续推进”。`
