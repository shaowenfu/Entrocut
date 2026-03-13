# 2026-03-13 Agent Runtime 落地开发日志

这份日志紧接 [2026-03-09_agent_runtime_notes.md](./2026-03-09_agent_runtime_notes.md)。

如果说 3 月 9 日那份笔记主要记录的是“为什么要从局部契约切到完整 `agent runtime（智能体运行时）` 视角”，那么这次我做的事情，本质上就是把那次讨论真正压进文档、类型、状态机和最小可运行代码里。

这不是一次普通的“补功能”开发。更准确地说，这一轮我做的是：

`把一个还停留在概念层的 editing agent，收敛成一套已经有明确骨架、清晰边界、并且能最小运行起来的系统。`

我在这轮开发里反复提醒自己一件事：

我不是在给当前页面加几个 `AI` 按钮，也不是在堆一些“以后可能有用”的抽象层。我在做的是把这个项目未来几年都绕不开的运行时骨架先钉住。

---

## 1. 我这轮开发的起点

起点其实不是代码，而是一个持续加深的认识：

我们前面几轮已经把很多关键点讨论明白了，但那些点还没有被真正串起来。

比如：

1. `Storyboard` 不该是事实源，`EditDraft` 才应该是
2. `clip / shot / scene` 的分层已经明确
3. `retrieval_request / edit_draft_patch / selection_context` 这些局部契约也已经接近稳定
4. 我们也已经开始用五层来理解整个 `editing agent`

但如果这些东西只是零散存在，它们仍然不是一个 agent。

我当时越来越明确地感到，真正的问题不是“有没有 schema”，而是：

`这些 schema 如何围绕一次持续工作的任务闭环组织起来。`

所以这轮工作的真正主题不是“继续补某个局部文档”，而是：

`把 State / Planner / Tool / Memory-Context / Execution Loop 这五层真正推到可落地状态。`

---

## 2. 我先重新从 chat-to-cut 推导 State Layer

这一步对我来说非常关键。

虽然我们已经有了很多 store 和页面状态，但我不想直接把已有字段拼一拼就叫它 `runtime state`。那样做只是把历史包袱重新打包一遍，不是真正的第一性原理推导。

我重新从 `chat-to-cut（对话到剪辑）` 这个理念出发，问自己：

如果用户是通过持续聊天推动视频剪辑，那系统每一轮到底必须记住哪些事实？

最后我把这个问题收敛成了 6 类状态：

1. `Goal State`
2. `Draft State`
3. `Selection State`
4. `Retrieval State`
5. `Execution State`
6. `Conversation State`

这个结论让我比较满意，不是因为它“看起来完整”，而是因为它刚好对应了 `chat-to-cut` 最小闭环里的 6 个问题：

1. 用户到底想做什么
2. 当前剪到什么版本
3. 当前在改哪里
4. 当前找素材进行到哪
5. 系统刚刚做了什么
6. 哪些对话结论已经被吸收

我把这一步落成了 [03_state_layer_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/03_state_layer_design.md)。

更重要的是，我没有停在文档里。我马上把它代码化成了：

- [sessionRuntimeState.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/sessionRuntimeState.ts)

这一步里我刻意做了两件事：

1. 先独立模块，不硬塞进现有 `workspace store`
2. 先做最小更新语义，而不是急着接复杂 planner

于是这份模块里先有了：

1. `SessionRuntimeState`
2. `createEmptySessionRuntimeState`
3. `syncRuntimeStateFromWorkspace`
4. `updateSelectionState`
5. `recordExecutionAction`

我当时的思路很明确：

`先把“运行时事实板”定成代码里的对象，再谈谁来消费它。`

随后我把它最小接进了 [useWorkspaceStore.ts](/home/sherwen/MyProjects/Entrocut/client/src/store/useWorkspaceStore.ts)，并让页面里的 `scene` 选中开始写回 `runtimeState.selection`。

这一步虽然不 flashy（不花哨），但我认为是这轮最重要的落地之一。因为从这一刻起，`runtimeState` 不再只是纸面设计，而开始进入现有事件驱动状态机。

---

## 3. 我把 Planner Layer 从“动作列表”推进到了“结构化输出”

前面的讨论已经把 `planner actions` 定得比较清楚了：

1. `reply_only`
2. `ask_clarification`
3. `update_goal`
4. `set_selection_context`
5. `create_retrieval_request`
6. `inspect_candidates`
7. `apply_patch`
8. `render_preview`

但我很快意识到，只停在动作列表是不够的。

问题不在于“planner 可以做哪些事”，而在于：

`planner 如何把“下一步决定”表达成一个系统能验证、能路由、能执行的对象。`

所以我继续把这层推进成了 [14_planner_output_schema.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/14_planner_output_schema.md)。

我最终把 `planner output` 收敛成三层：

1. `header`
2. `payload`
3. `meta`

这个结构当时对我来说是一个很重要的收束点。

因为它说明：

1. `planner` 的输出不是自然语言
2. 也不是底层工具参数
3. 而是“下一步系统行为”的结构化决议

随后我把它代码化成了：

- [plannerOutput.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/plannerOutput.ts)

里面先做了：

1. `PlannerOutput` 类型
2. 与后续工具契约对齐的 payload 类型
3. 最小 `validatePlannerOutput`
4. 后来又补了更强的 `normalizePlannerOutput`

我刻意没有把它做成一堆复杂泛型，也没有为了“类型优雅”过度抽象。我优先追求的是：

`只要它能稳定承载执行闭环需要的语义，就够了。`

---

## 4. Tool Layer 我先坚持“高层工具，不直暴露底层能力”

这一部分的思考很大程度上来自我们前面的讨论。

当时有一个诱惑是：既然要做视频 agent，那要不要把 `ffmpeg trim`、向量检索、多模态问答这些底层能力直接抬上来？

我最后没有这么做。

原因很直接：

如果让 `planner` 直接看到太多底层媒体能力，系统会很快失控，分层也会被打穿。

所以我把 `Tool Layer` 先收敛成了 5 类高层工具：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

并分别落了字段级文档：

- [06_read_tool_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/06_read_tool_contract.md)
- [07_retrieval_request_schema.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/07_retrieval_request_schema.md)
- [08_inspect_tool_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/08_inspect_tool_contract.md)
- [09_edit_draft_patch_schema.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/09_edit_draft_patch_schema.md)
- [10_preview_tool_contract.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/10_preview_tool_contract.md)

我当时特别想钉住的一点是：

`planner-facing tools（面向规划器的工具）` 和 `execution backend capabilities（执行后端能力）` 必须分离。

也就是说：

1. `planner` 只应该看到高层工具
2. 底层向量检索、多模态判断、`ffmpeg` 拼接这些属于工具内部实现

这一步很重要，因为它保护了后面所有演进空间。

---

## 5. Memory / Context Layer 是我这轮花了最多精力思考的一层

我越来越确认：

这层不是附属品，它是整套系统最容易被做烂、但也最决定上限的一层。

我一开始就提醒自己，不要把这层简单理解成“给 prompt 塞上下文”。

从第一性原理出发，我把它定义成：

`把长期任务连续性和单轮可决策性接起来的那层。`

随后我先落了总设计：

- [11_memory_context_layer_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/11_memory_context_layer_design.md)

然后把其中最关键的两个对象继续拆开：

1. [12_action_context_packet_schema.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/12_action_context_packet_schema.md)
2. [13_context_assembler_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/13_context_assembler_design.md)

我对这部分最在意的不是“字段有多少”，而是两个原则：

1. `State` 和 `Context` 必须分离
2. 上下文必须按动作装配，而不是给一个固定大模板

我最后把 `ActionContextPacket` 定义成：

`模型在当前这一轮、为了完成某个具体动作而被允许看到的最小工作事实包。`

这一定义让我很满意，因为它把很多模糊说法都收住了。

随后我把它继续代码化成了：

- [contextAssembler.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/contextAssembler.ts)

这一步我刻意做成纯函数，没有一开始就耦合进页面或 planner。

它当前已经能真实根据：

1. `runtimeState`
2. 当前 `actionType`
3. 最近候选和失败

生成：

1. `task_summary`
2. `goal_summary`
3. `draft_excerpt`
4. `candidate_excerpt`
5. `recent_failures`
6. `recent_actions`
7. `available_tools`

我当时的动机很明确：

`先让上下文装配成为一个可以单独被讨论、被测试、被替换的模块。`

这样后面接真实 LLM 时，我就不会再回到“随手拼 prompt”的老路。

---

## 6. Execution Loop 是我把“分层设计”变成“运行系统”的那一步

当 `State / Planner Output / Tool Contracts / Context Assembler` 都已经定下来后，我当时最强烈的感觉是：

这些东西都已经有了，但它们还是静态部件。

真正缺的最后一层是：

`谁来把“状态 -> 上下文 -> 决议 -> 执行 -> 回写”固定成一个运行周期？`

于是我把 `Execution Loop` 继续收束成了：

- [15_execution_loop_design.md](/home/sherwen/MyProjects/Entrocut/docs/agent_runtime/15_execution_loop_design.md)

我最终把它定成了 7 个阶段：

1. `Observe`
2. `Assemble`
3. `Plan`
4. `Validate`
5. `Act`
6. `Write Back`
7. `Continue or Stop`

随后我把它代码化成了：

- [executionLoop.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/executionLoop.ts)

这里我刻意采取了“单步事务优先”的策略。

也就是说：

1. 先做 `runExecutionStep`
2. 再做受控多步的 `runExecutionLoop`

而不是一上来做复杂状态机或并发编排。

我当时很清楚一件事：

`只要单步事务不稳，多步自动推进一定会变成灾难。`

所以这层代码里，我优先钉住了：

1. 上下文装配失败怎么停
2. planner 输出无效怎么停
3. 工具执行失败怎么停
4. 哪些动作写状态、哪些动作走工具
5. 执行结果怎么写回 `runtimeState`

这一步完成之后，我第一次感觉：

这已经不再只是“架构讨论”，而开始像一个真正的 agent runtime 了。

---

## 7. 然后我开始接第一版真实 planner 和第一版真实 tool executor

这里我故意没有继续停留在纯抽象层。

因为到这个阶段，如果还只是在写文档，就会失去工程反馈。

所以我开始问自己：

在不引入过多复杂度的前提下，怎样才能让这条链真正动起来？

我的答案是：

1. 先做一个启发式但真实的 `planner runner`
2. 先做一个本地可执行的 `tool executor`
3. 先让它能真的改 `runtimeState` 和 `EditDraft`

于是我新增了：

- [plannerRunner.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/plannerRunner.ts)
- [toolExecutor.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/toolExecutor.ts)

我当时对“真实”的定义很克制：

不是“接真实大模型就算真实”，而是：

`它是否真的基于当前上下文做决策，并真的改变当前运行时状态。`

所以这第一版里：

1. `plannerRunner`
   - 会基于 `ActionContextPacket` 产出真正的 `PlannerOutput`
2. `toolExecutor`
   - 会真实更新：
     - `candidatePool`
     - `candidatePoolStatus`
     - `EditDraft.shots`
     - `draftVersion`
     - `previewDraftVersion`

我刻意先做了本地 lexical ranking（词法排序）和本地 patch 回写，而没有急着接复杂后端。

原因很简单：

`先把 agent runtime 的闭环跑通，比先接复杂 provider 能力更重要。`

---

## 8. 接着我把 runAgentLoop 暴露到 UI，并把 heuristic planner 升级成真实 LLM planner

这一段是我觉得整轮开发里最关键的“从骨架走向实际系统”的一步。

我先在 `workspace store` 里暴露了：

1. `assembleActionContext`
2. `runAgentLoop`

然后在页面上加了一个最小的开发入口：

- `Run Agent`

这样我就能从 UI 上直接触发：

`Context Assembler -> Planner -> Execution Loop -> Tool Executor -> runtimeState`

这一步虽然只是加了一个按钮，但它的意义很大：

`意味着这整套 agent runtime 已经不再只是代码模块，而是进入了当前产品交互链路。`

随后，我没有满足于启发式 planner，而是把它继续替换成了“优先真实 LLM planner，失败回退 heuristic planner”的模式。

为此我新增了：

- [llmPlannerRunner.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/llmPlannerRunner.ts)

我刻意让它直接走现有的 `server /v1/chat/completions`，继续沿用：

1. `ActionContextPacket`
2. `PlannerOutput`
3. `ExecutionLoop`

也就是说，我没有推翻骨架，只是在骨架中替换 planner 实现。

这一步对我来说很重要，因为它验证了我们前面的设计没有白费：

`Context Assembler -> PlannerOutput -> ExecutionLoop`

这条链确实可以承接从启发式 planner 到真实 LLM planner 的切换。

---

## 9. 最后我重点加固了 planner 的 prompt 和 JSON 解析

接上真实 LLM 之后，一个新问题立刻冒出来：

`如果模型输出不稳，这条闭环随时会塌。`

所以我没有继续往后堆功能，而是先回头加固 planner 这一层最脆弱的地方：

1. prompt 约束
2. JSON 提取
3. 输出归一化
4. 强校验
5. 失败重试
6. 回退机制

这部分改动主要落在：

- [llmPlannerRunner.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/llmPlannerRunner.ts)
- [plannerOutput.ts](/home/sherwen/MyProjects/Entrocut/client/src/agent/plannerOutput.ts)

我做了几件关键事：

### 9.1 Prompt 更硬

我明确要求模型：

1. 只能返回单个 JSON 对象
2. 顶层只能有 `header / payload / meta`
3. `action` 与 `payload.kind` 必须严格匹配
4. 某些动作的关键字段必须存在

这不是为了“提示词更优雅”，而是为了尽量减少进入解析层前的随机性。

### 9.2 JSON 解析更稳

我没有再满足于简单的：

1. 去 code fence
2. `JSON.parse`

而是补了：

1. `stripCodeFence`
2. `extractJsonObject`
3. `normalizePlannerOutput`

这意味着：

即使模型前后带了点噪声，只要中间还有一个平衡 JSON 对象，我们就有机会恢复。

### 9.3 校验更强

我在 `plannerOutput.ts` 里继续补强了：

1. `INVALID_ACTION`
2. 更严的 `target_scope` 校验
3. payload 一致性校验

例如：

1. `clarification.questions` 不能为空
2. `selection_update` 缺 `scene_id / shot_id` 会报错
3. `retrieval_request` 必须带 `query / policy`
4. `candidate_inspection` 必须带 `candidates`
5. `edit_draft_patch` 必须带 `operations`
6. `preview_request` 必须带 `draft_version`

### 9.4 自动修复重试

如果模型输出第一次不合法，我没有直接失败，而是：

1. 带上上一轮无效输出
2. 带上验证错误列表
3. 再发起 repair retry（修复重试）

最多重试两轮。

### 9.5 失败回退

如果重试之后仍然不合法，则回退到启发式 planner。

这一点我很看重，因为开发阶段我不能接受：

`只要 LLM 一次输出不稳，整个 agent loop 就完全不可用。`

---

## 10. 我对这一轮开发的总体判断

这一轮结束之后，我对项目状态的判断比之前清晰很多。

我认为我们已经跨过了一个关键门槛：

`从“围绕智能剪辑 agent 的高密度概念讨论”，进入了“这套 runtime 架构已经以文档、类型、状态机、执行器和最小 UI 入口形式存在”的阶段。`

这并不意味着 agent 已经成熟。恰恰相反，我认为现在还有很多明显边界：

1. `planner` 仍然非常脆弱，虽然比之前稳了很多
2. `tool executor` 还是本地简化实现，没有接真实后端检索与真实预览执行
3. 现在的 `Run Agent` 仍是开发入口，不是产品级交互
4. 失败信息虽然进入了代码层，但还没有完整暴露到 UI 和调试面板

但我认为方向是对的。

更重要的是，这次没有再走“先堆一个功能、以后再重构”的老路。

我始终围绕一个原则在推进：

`先把运行时边界和执行闭环定稳，再让具体智能能力往里填。`

---

## 11. 当前我认为最值得继续推进的方向

基于这轮工作的结果，我认为下一步最值的事情有三类：

### 11.1 提高 planner 可观测性

我希望后面能更直接看到：

1. 当前 prompt 是什么
2. 模型原始输出是什么
3. 校验失败在哪里
4. 为什么回退到了 heuristic planner

这是下一步稳定 LLM planner 的基础。

### 11.2 把 tool executor 继续接到真实能力

尤其是：

1. 真实 `retrieve`
2. 真实 `preview`

否则现在还只能验证 runtime 架构，而不能验证产品级效果。

### 11.3 逐步让页面从局部状态迁到 runtime state

现在仍然有一部分页面选中态、预览态留在局部 `useState` 里。

我认为后面应该继续把真正影响 agent 决策的那部分交互状态，逐步挪回 `runtimeState`。

---

## 12. 最后的回顾

如果让我用一句话总结这整个 session 的推进过程，我会说：

我做的不是“给现有视频编辑原型接了点 AI”，而是：

`把这个项目的智能剪辑能力，从零散的想法、局部 schema 和概念设计，推进成了一套已经具备 runtime 边界、上下文装配、规划输出、工具契约、执行闭环、真实 LLM 接口和最小 UI 入口的系统骨架。`

这套骨架当然还很早期，也远没有到产品成熟阶段。

但从工程视角看，我认为最难的一部分已经不是“能不能写出来某个功能”，而是：

`我们已经知道系统的骨架应该长什么样，而且这套骨架已经开始在代码里站住了。`
