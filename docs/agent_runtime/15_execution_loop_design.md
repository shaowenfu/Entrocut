# Execution Loop Design

本文档不再讨论抽象层面的 `Execution Loop（执行闭环）`。

它直接回答当前仓库里最现实的问题：

`core/server.py` 里的 `_run_chat_agent_loop` 现在只有 `planner loop skeleton（规划循环骨架）`，如果要把它改成一个真正可持续推进任务的最小闭环，应该怎么改？

本文档的目标不是设计最终生产形态，而是给当前 `core` 提供一条最短、最稳、最少概念膨胀的落地路径。

---

## 1. 当前代码的真实状态

当前 `core/server.py` 已经具备这些能力：

1. 能读取当前 `project / edit_draft / chat_turns`
2. 能组装 `planner context`
3. 能调用 `server /v1/chat/completions`
4. 能解析结构化 `PlannerDecisionModel`
5. 能在 `decision.status == "final"` 时结束
6. 能在 `decision.status == "requires_tool"` 时显式报 `TODO`

所以当前 `_run_chat_agent_loop` 实际上是：

`assemble -> plan -> final / fail`

而不是：

`assemble -> plan -> act -> observe -> replan -> stop`

缺失的核心层只有 4 个：

1. `tool dispatch（工具分发）`
2. `tool result normalization（工具结果规范化）`
3. `state write-back in loop（循环内状态回写）`
4. `replanning after observation（观测后的重新规划）`

---

## 2. 当前阶段的第一性原理

对当前项目而言，`Execution Loop` 最重要的职责不是“多调用几次模型”，而是：

`把一次 chat 请求稳定推进成“状态 -> 决策 -> 执行 -> 新状态”的有限步闭环。`

这意味着：

1. 每一轮必须围绕一个明确状态版本工作
2. 每一轮最多执行一个明确动作
3. 动作结果必须先被程序规范化，再回写状态
4. 下一轮只能基于新的事实重规划
5. 整个过程必须有清晰停止条件和错误语义

如果不满足这 5 点，系统就只是一个“会循环的 planner”，不是真正的 `agent`

---

## 3. 当前最小闭环的建议目标

当前仓库不需要一步到位做成通用 `agent framework（智能体框架）`。

最小目标应该非常克制：

1. 保留当前 `_run_chat_agent_loop` 的函数位置和主入口
2. 保留当前 `PlannerDecisionModel` 的基本返回方式
3. 只新增最少的执行中间层
4. 只接入当前文档里已经讨论过的高层工具边界
5. 先支持 `retrieve / inspect / patch / preview`
6. 不在这一轮引入数据库、任务队列、复杂并发控制

一句话：

`先把 core/chat 从“planner-only”升级成“single-step tool-capable loop”，而不是直接做大而全运行时框架。`

---

## 4. 推荐的最小执行阶段

当前阶段建议把 `_run_chat_agent_loop` 固定为 8 个阶段。

### 4.1 Load State

读取当前轮真正需要的最小状态：

1. `project`
2. `edit_draft`
3. 最近聊天摘要
4. `target`
5. 当前循环内累积的 `observations`

目的：

1. 保证每轮基于同一份明确事实工作

### 4.2 Assemble Context

组装发给 `planner` 的上下文包。

除现有内容外，必须补上：

1. 当前轮之前的 `tool observations`
2. 当前允许使用的工具清单
3. 当前停止条件

目的：

1. 让 `planner` 看到“已经做了什么”和“还允许做什么”

### 4.3 Plan

调用 `server /v1/chat/completions` 获取结构化决策。

当前建议仍保持：

1. `status`
2. `reasoning_summary`
3. `assistant_reply`
4. `tool_name`
5. `tool_input_summary`
6. `draft_strategy`

但需要新增一个真正可执行的字段：

1. `tool_payload`

否则 `tool_input_summary` 只能给人看，不能给程序执行。

### 4.4 Validate Decision

模型输出不能直接执行，必须先做程序侧校验：

1. `status` 是否合法
2. `tool_name` 是否在允许集合内
3. `tool_payload` 是否符合对应 `schema`
4. 当前状态是否允许执行这个工具
5. 当前轮次是否已超预算

目的：

1. 把“模型说了什么”和“系统允许做什么”分开

### 4.5 Execute Tool

如果 `status == "requires_tool"`，则由 `core` 代码执行工具。

注意：

1. 执行的是高层语义工具
2. 不让 `planner` 直接接触底层实现细节

当前建议的最小路由：

1. `retrieve`
2. `inspect`
3. `patch`
4. `preview`

### 4.6 Normalize Observation

工具执行后，不能把原始结果直接拼回 prompt。

必须先收敛成统一的 `ToolObservation（工具观测）`：

1. `tool_name`
2. `success`
3. `summary`
4. `artifacts`
5. `state_delta`
6. `error`

目的：

1. 让后续 `planner` 看到标准化结果
2. 让状态回写具备稳定契约

### 4.7 Write Back

把执行结果回写到循环内状态。

最小回写包括：

1. 更新循环内 `current_draft`
2. 记录 `observations`
3. 记录 `step trace`

如果工具本身已经产生确定性状态变化，例如 `patch`，则必须把变化写入下一轮要看到的 `draft`

### 4.8 Continue or Stop

每轮结束后固定做一次判断：

1. `decision.status == "final"` 则结束
2. 连续失败则结束
3. 达到最大轮次则结束
4. 工具执行成功但仍需下一步，则继续

---

## 5. 当前项目最小闭环的推荐形状

推荐把当前执行链固定成：

`draft state -> planner decision -> tool execution -> normalized observation -> draft/state update -> replanning`

更具体地说：

`user prompt`
-> `assemble planner context`
-> `planner returns final or tool request`
-> `core executes tool`
-> `core normalizes tool result`
-> `core updates current_draft / observations`
-> `planner sees updated state`
-> `planner returns next step or final`

这才是当前项目真正需要的最小 `agent loop`

---

## 6. 推荐的数据结构增量

当前不建议大改全局架构，只建议在 `core/server.py` 附近增加三个最小结构。

### 6.1 `ToolCallModel`

```python
class ToolCallModel(BaseModel):
    tool_name: Literal["retrieve", "inspect", "patch", "preview"]
    payload: dict[str, Any]
```

作用：

1. 把“要调用什么工具”和“调用参数”结构化

### 6.2 `ToolObservationModel`

```python
class ToolObservationModel(BaseModel):
    tool_name: str
    success: bool
    summary: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    state_delta: dict[str, Any] = Field(default_factory=dict)
    error: ErrorBody | None = None
```

作用：

1. 统一承接工具输出
2. 为 replan 提供稳定输入

### 6.3 `AgentLoopResultModel`

```python
class AgentLoopResultModel(BaseModel):
    final_decision: PlannerDecisionModel
    final_draft: EditDraftModel
    observations: list[ToolObservationModel]
    iterations_used: int
```

作用：

1. 让 `_run_chat_agent_loop` 不再只返回 `decision`
2. 而是返回“这一轮闭环真正产出的结果”

---

## 7. 推荐的最小代码拆分

当前最稳的做法不是重写整个 `core`，而是在 `core/server.py` 内先把 `_run_chat_agent_loop` 周边拆成 4 个辅助函数。

### 7.1 `_validate_planner_decision(...)`

负责：

1. 决策字段校验
2. 工具名校验
3. `tool_payload` 的基础合法性校验

### 7.2 `_execute_tool_call(...)`

负责：

1. 根据 `tool_name` 路由到对应执行逻辑
2. 返回统一 `ToolObservationModel`

### 7.3 `_apply_observation_to_draft(...)`

负责：

1. 根据 `state_delta` 更新 `current_draft`
2. 保证 `draft` 版本和字段变更统一收口

### 7.4 `_should_continue_agent_loop(...)`

负责：

1. 根据当前决策、错误、轮次预算决定继续还是停止

这样做的好处是：

1. 不改主入口结构
2. 不引入跨文件跳跃
3. 先把职责从一个大函数里分离出来

---

## 8. 推荐的 `_run_chat_agent_loop` 最小重构形态

重构后建议的伪代码如下：

```python
async def _run_chat_agent_loop(...) -> AgentLoopResultModel:
    current_draft = draft
    observations = []

    emit("loop_started")

    for iteration in range(1, AGENT_LOOP_MAX_ITERATIONS + 1):
        emit("planner_context_assembled")

        decision = await _request_server_planner_decision(
            ...,
            draft=current_draft,
            observations=observations,
            iteration=iteration,
        )

        validated = _validate_planner_decision(decision, current_draft)
        emit("planner_decision_received")

        if validated.status == "final":
            return AgentLoopResultModel(
                final_decision=validated,
                final_draft=current_draft,
                observations=observations,
                iterations_used=iteration,
            )

        observation = await _execute_tool_call(
            project_id=project_id,
            access_token=access_token,
            decision=validated,
            draft=current_draft,
        )
        observations.append(observation)
        emit("tool_observation_recorded")

        if not observation.success:
            raise CoreApiError(...)

        current_draft = _apply_observation_to_draft(current_draft, observation)
        emit("draft_updated_in_loop")

    raise CoreApiError(...)
```

这个结构相较当前代码只多了 3 件事：

1. 真执行工具
2. 真回写状态
3. 真基于新状态重规划

已经足够让 `core/chat` 从骨架升级为闭环。

---

## 9. 与当前 `_run_chat` 的衔接方式

为了最小改动，`_run_chat` 不需要重写，只需要把它依赖的返回值从：

`PlannerDecisionModel`

改成：

`AgentLoopResultModel`

然后：

1. 使用 `loop_result.final_decision`
2. 使用 `loop_result.final_draft`
3. 把 `loop_result.observations` 追加进 assistant `ops` 或事件数据

这样可以把“循环内的草案更新”和“循环结束后的最终落盘”分开。

建议边界：

1. `_run_chat_agent_loop` 只负责循环内推进
2. `_run_chat` 只负责把最终结果写入 `record` 和广播事件

---

## 10. 当前阶段明确不做的事

为了控制复杂度，这一轮最小重构明确不做：

1. 不做持久化 `checkpoint（检查点）`
2. 不做跨进程任务恢复
3. 不做并行工具调度
4. 不做通用 `tool registry（工具注册中心）`
5. 不做复杂 `memory compaction（记忆压缩）`
6. 不把 `core/server.py` 立即拆成多文件架构

这很重要。

当前最关键的不是“把系统设计得很完整”，而是：

`先让真实 planner -> tool -> observation -> replanning 这条主链在 core 里跑通。`

---

## 11. 建议的落地顺序

如果按最小风险推进，建议顺序如下：

1. 给 `PlannerDecisionModel` 增加 `tool_payload`
2. 新增 `ToolCallModel / ToolObservationModel / AgentLoopResultModel`
3. 改造 `_build_planner_messages`，把 `observations` 和允许工具清单送进上下文
4. 新增 `_validate_planner_decision`
5. 新增 `_execute_tool_call`
6. 新增 `_apply_observation_to_draft`
7. 把 `_run_chat_agent_loop` 改成真正的 `plan -> act -> observe -> replan`
8. 最后再改 `_run_chat` 的结果承接

这个顺序的好处是：

1. 契约先行
2. 单步可验证
3. 不会一次性改坏整条 chat 主链

---

## 12. 一句话结论

当前 `_run_chat_agent_loop` 最大的问题不是“循环轮次太少”，而是：

`它没有在循环内部真正改变世界。`

所以当前最小重构的目标不是让它“更智能”，而是让它第一次具备真正闭环的基本条件：

`planner 能请求动作`
`core 能执行动作`
`执行结果能回写状态`
`planner 能基于新状态继续思考`

做到这一点，`core/chat` 才算从 `planner skeleton` 进入了真正的 `agent loop`
