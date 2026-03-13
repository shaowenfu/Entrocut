# Execution Loop Design

本文档定义当前项目 `editing agent（剪辑智能体）` 的 `Execution Loop（执行闭环）`。

目标不是描述一个抽象循环，而是固定：

1. `Execution Loop` 从第一性原理上在做什么
2. 为什么它是让前面所有层真正运行起来的最后一层
3. 它的最小执行阶段、输入输出、继续/停止条件和失败语义是什么
4. 当前阶段推荐的最小实现边界是什么

本文档只定义执行闭环的结构，不展开具体模型调用、任务队列、并发调度或网络协议。

---

## 1. 第一性原理

前面的层已经回答了这些问题：

1. `State Layer`
   - 当前事实是什么
2. `Memory / Context Layer`
   - 当前动作需要看到什么
3. `Planner Layer`
   - 下一步应该做什么
4. `Tool Layer`
   - 这一步具体怎么执行

但系统仍然缺一个关键能力：

`怎么把“当前事实 -> 当前决议 -> 当前执行结果 -> 新事实”稳定串成一次真正推进任务的运行周期？`

这个能力就是 `Execution Loop`。

一句话定义：

`Execution Loop` 是把“状态 -> 上下文 -> 决议 -> 执行 -> 回写 -> 继续/停止”固定成单步事务循环的运行时总控层。`

---

## 2. 它的本质是什么

`Execution Loop` 的本质不是简单的 `while` 循环，而是：

`a controlled step transaction runner（受控的单步事务执行器）`

每一轮都应像一个小事务：

1. 基于某个状态版本开始
2. 只围绕这份状态生成一个上下文包
3. 产出一个结构化决议
4. 执行一个明确动作
5. 把结果回写成新的状态版本
6. 再判断是否进入下一轮

所以它必须同时保证：

1. 一致性
2. 可中断
3. 可回放

---

## 3. 为什么必须单独设计

如果没有显式 `Execution Loop`，系统通常会退化成三种坏形态：

### 3.1 Planner-only

`planner` 产出结果后就结束。

问题：

1. 只有决议，没有持续推进

### 3.2 Tool-sprawl

工具调用散落在页面、store、服务层各处。

问题：

1. 没有统一校验
2. 没有统一回写
3. 没有统一停止条件

### 3.3 One-shot interaction

每次交互都是一次性的，不形成真正 agent 闭环。

问题：

1. 不能持续多步推进
2. 不能稳定处理中间结果

所以必须有一层把所有步骤统一起来。

---

## 4. 最小执行阶段

当前阶段推荐固定为 7 个阶段。

### 4.1 Observe

读取当前最新 `runtimeState`

目的：

1. 确保这一轮围绕同一事实版本工作

### 4.2 Assemble

调用 `Context Assembler` 生成 `ActionContextPacket`

目的：

1. 把全量事实压缩成当前动作输入

### 4.3 Plan

调用 `planner`，得到 `PlannerOutput`

目的：

1. 决定下一步动作

### 4.4 Validate

校验：

1. `PlannerOutput` schema 是否合法
2. `action / payload / scope` 是否一致
3. 当前状态是否允许执行

目的：

1. 阻止非法决议直接落地

### 4.5 Act

根据动作类型，路由到：

1. 状态动作
2. 工具动作

目的：

1. 真正执行当前一步

### 4.6 Write Back

把执行结果规范化后写回新的 `runtimeState`

目的：

1. 让下一轮基于最新事实继续

### 4.7 Continue or Stop

判断：

1. 是否要继续自动推进
2. 是否必须等待用户
3. 是否因错误而停止

目的：

1. 结束本轮并决定后续

---

## 5. 整体闭环

推荐执行链写成：

`runtimeState -> ActionContextPacket -> PlannerOutput -> validate -> route/act -> writeBack -> nextRuntimeState`

如果进一步压缩，本质就是：

`state -> decide -> act -> state`

这是当前项目真正意义上的最小 agent 闭环。

---

## 6. 输入与输出

### 6.1 单步执行输入

```ts
interface ExecutionStepInput {
  runtime_state: SessionRuntimeState;
  action_type: PlannerActionType;
  max_auto_steps?: number;
  step_started_at: string;
}
```

这里真正重要的是：

1. 当前状态
2. 当前动作类型
3. 当前这一轮的启动时间

### 6.2 单步执行输出

```ts
interface ExecutionStepResult {
  success: boolean;
  planner_output?: PlannerOutput;
  action_context_packet?: ActionContextPacket;
  next_runtime_state: SessionRuntimeState;
  should_continue: boolean;
  wait_for_user: boolean;
  stop_reason: string;
}
```

设计理由：

1. 需要返回本轮实际用了什么上下文
2. 需要返回本轮实际产出的决议
3. 需要返回新的状态
4. 需要明确是继续、等待用户还是出错停止

---

## 7. Router（路由）原则

`Execution Loop` 自己不发明业务动作，只负责把 `PlannerOutput` 路由到正确执行面。

当前建议分两类：

### 7.1 State Actions

包括：

1. `reply_only`
2. `ask_clarification`
3. `update_goal`
4. `set_selection_context`

特点：

1. 主要写回状态
2. 不依赖外部工具结果

### 7.2 Tool Actions

包括：

1. `create_retrieval_request`
2. `inspect_candidates`
3. `apply_patch`
4. `render_preview`

特点：

1. 需要路由到工具层
2. 工具结果要先规范化，再回写状态

因此 router 的本质是：

`action -> state update path | tool execution path`

---

## 8. Continue / Stop 的判断原则

不是每执行一步都继续自动跑，也不是每一步都停。

正确原则如下：

### 8.1 应继续

当当前系统还处在一个明确未完成的自动子任务中，例如：

1. 已经生成检索请求，下一步需要 inspect
2. 已经 inspect 完，下一步需要 patch
3. 已经 patch 完，下一步需要 preview

### 8.2 应停止

当下一步必须等待外部输入，例如：

1. 需要用户澄清
2. 需要用户审阅预览
3. 当前任务已达到局部完成态
4. 发生了阻断性错误

所以：

`Execution Loop` 的目标不是无限自动推进，而是在可自主推进时小步连跑，在需要人类输入时稳定停下。`

---

## 9. 最佳实践

### 9.1 Single-step first

先把单步执行做成稳定事务，再考虑多步自动链。

### 9.2 Validate before act

必须先校验 `PlannerOutput`，再执行。

### 9.3 Write normalized results

回写的一定是规范化结果，不是原始工具输出。

### 9.4 Version-aware execution

每轮都必须围绕明确的状态版本和草案版本执行。

### 9.5 Interruptible by user

用户新的输入必须能打断当前后续自动链。

### 9.6 Log every step

每轮至少要能记录：

1. 当前动作类型
2. 当前上下文包摘要
3. `PlannerOutput`
4. 执行结果
5. 停止原因

---

## 10. 失败语义

`Execution Loop` 需要自己的最小错误语义。

```ts
type ExecutionLoopErrorCode =
  | "CONTEXT_ASSEMBLY_FAILED"
  | "PLANNER_FAILED"
  | "PLANNER_OUTPUT_INVALID"
  | "ROUTING_FAILED"
  | "TOOL_EXECUTION_FAILED"
  | "WRITEBACK_FAILED";

interface ExecutionLoopError {
  code: ExecutionLoopErrorCode;
  message: string;
  action_type?: string;
}
```

其中：

1. `CONTEXT_ASSEMBLY_FAILED`
   - 无法装配本轮上下文
2. `PLANNER_FAILED`
   - planner 自身失败
3. `PLANNER_OUTPUT_INVALID`
   - planner 输出无法通过校验
4. `ROUTING_FAILED`
   - 无法确定路由目标
5. `TOOL_EXECUTION_FAILED`
   - 工具执行失败
6. `WRITEBACK_FAILED`
   - 结果无法写回新状态

---

## 11. 当前阶段推荐实现边界

当前阶段不应该一开始就做复杂并发和多步图执行。

建议先实现：

1. `runExecutionStep`
   - 跑一轮单步事务
2. `runExecutionLoop`
   - 在受控条件下多跑几步
3. 最小 router
   - 区分 state actions 和 tool actions
4. 最小 write-back 协议
   - 把结果回写到 `runtimeState`

不要先做：

1. 多代理协作
2. 并发工具编排
3. 复杂依赖图调度
4. 自动回退恢复

---

## 12. 一句话结论

`Execution Loop` 的本质，是一个把“状态 -> 上下文 -> 决议 -> 执行 -> 回写 -> 继续/停止”固定成单步事务循环的运行时总控层；没有它，前面的分层只是静态设计，不是真正工作的 agent。`
