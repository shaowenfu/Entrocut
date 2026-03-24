# 2026-03-24 项目回顾与阶段性暂停日志

这篇日志的目标不是记录某一个小功能，而是把这段时间项目真正推进过的主线重新串起来，给未来的我一个能快速重新进入状态的入口。

我现在回头看，这一轮项目推进其实经历了 5 个清晰阶段：

1. 清场式重构，重新定义最小闭环
2. 用 `EditDraft` 取代 `Storyboard`，重新固定剪辑事实源
3. 从局部契约讨论，升级到完整 `agent runtime（智能体运行时）` 设计
4. 把 `agent runtime` 的主骨架文档化、类型化、代码化
5. 继续往 `server toolchain（服务端工具链）` 推进，但在 `core /chat` 主链上发现方向性问题，必须先停下来收口

这篇日志就是围绕这 5 件事展开。

---

## 1. 第一阶段：我先做了一次清场式重构

这轮推进的真正起点，不是加功能，而是承认旧结构已经不值得修补。

我当时最强烈的判断是：

`如果继续在旧的 core/server、旧测试、旧 contract 层上小修小补，我只会不断给错误结构续命。`

所以我先做了清场，保留的东西非常克制：

1. 前端原型 `UI`
2. `Launchpad / Workspace` 的状态层
3. 最小可运行的 `core/server.py` 和 `server/main.py`
4. 启动脚本和说明文档

删除掉的是旧业务目录、旧测试、旧事件层、旧实验性脚本。

这一阶段最重要的产出不是代码，而是一个重新建立起来的判断：

`当前系统最有价值的资产不是旧实现，而是前端已经长出来的产品状态机。`

也正是基于这个判断，我后面才会优先去写 `state model（状态模型）` 和 `Core API / WS contract（本地契约）`。

对应日志：

1. [2026-03-07_rebuild_journal.md](./2026-03-07_rebuild_journal.md)

---

## 2. 第二阶段：我把系统真实的剪辑事实源从 Storyboard 改成了 EditDraft

这一阶段的关键不是“字段改了什么”，而是我重新确认了系统到底围绕什么对象工作。

我越来越明确地意识到：

1. `Storyboard` 更像展示层对象，不像执行层对象
2. `scene -> clip` 的关系如果只靠页面下标去猜，后面做局部编辑一定会失真
3. 真正会被用户和 agent 修改的，不是 `clip` 本体，而是“本次草案里一次具体的使用”

于是这一轮我最终把剪辑结构固定成：

1. `Asset`
2. `Clip`
3. `Shot`
4. `Scene`
5. `EditDraft`

最重要的两个结论是：

1. `shot` 是最小可编辑语义单元
2. `scene` 是可选工作分组层，不是必选的创作模板

然后我把这套口径统一写进了：

1. [docs/editing/01_edit_draft_schema.md](../editing/01_edit_draft_schema.md)
2. [docs/contracts/01_core_api_ws_contract.md](../contracts/01_core_api_ws_contract.md)
3. `README.md`
4. `EntroCut_architecture.md`
5. `EntroCut_algorithm.md`

随后实现层也对齐到了这套口径：

1. `core/server.py` 不再围绕 `storyboard` 维护事实源，而是围绕 `edit_draft`
2. `client` 端以 `edit_draft` 为真实事实源，再派生出当前 UI 还在消费的 `storyboard` 展示视图

这一阶段的本质，不是“结构更复杂”，而是：

`系统终于开始围绕真实剪辑草案工作，而不是围绕展示卡片工作。`

对应日志：

1. [2026-03-08_edit_draft_contract_landing_journal.md](./2026-03-08_edit_draft_contract_landing_journal.md)

---

## 3. 第三阶段：我从局部契约设计切到了完整 agent runtime 视角

`EditDraft` 定下来之后，问题很快就变了。

我当时已经不再纠结某个字段怎么命名，而是开始反复问自己：

`这些 schema 到底怎么围绕一次持续工作的任务组织起来？`

这是整个项目认知升级最明显的一段。

前面几轮讨论里，先被打稳的是这些局部问题：

1. 为什么 `Storyboard` 不能是事实源
2. 为什么 `EditDraft` 必要
3. 为什么 `shot` 是最小可编辑单元
4. 为什么系统应该走 `retrieval-first（检索优先）`
5. `selection_context / retrieval_request / edit_draft_patch` 这些局部契约分别在做什么

这些讨论都没有错，但它们本质上是在给 `agent` 的：

1. `world model（世界模型）`
2. `tool boundary（工具边界）`
3. `execution object（执行对象）`

打地基。

真正的升级发生在我开始接受一个更完整的视角：

`editing agent` 必须按五层去理解：

1. `State Layer`
2. `Planner Layer`
3. `Tool Layer`
4. `Memory / Context Layer`
5. `Execution Loop`

这一步很重要，因为它让我不再把项目理解成：

1. 一堆 prompt
2. 一堆工具
3. 再加一点状态机

而是开始把它理解成一个真正会持续推进任务的 `agent runtime`。

对应笔记：

1. [2026-03-09_agent_runtime_notes.md](./2026-03-09_agent_runtime_notes.md)

---

## 4. 第四阶段：我把 agent runtime 从讨论推进到了文档、类型和最小运行代码

这一阶段是文档和代码同步推进的一轮。

### 4.1 我先从 chat-to-cut 重新推导 State Layer

我没有直接拿现有 store 的字段拼一个 `runtimeState`，而是重新从 `chat-to-cut（对话到剪辑）` 倒推：

如果用户通过多轮对话持续推动视频编辑，那系统每轮到底必须记住哪些事实？

我最后把它收敛成 6 类运行时状态：

1. `Goal State`
2. `Draft State`
3. `Selection State`
4. `Retrieval State`
5. `Execution State`
6. `Conversation State`

这一步后面被写成：

1. [docs/agent_runtime/03_state_layer_design.md](../agent_runtime/03_state_layer_design.md)

然后我又把它代码化成了前端的 `session runtime state` 骨架，并最小接进了 `workspace store`。

### 4.2 我把 Planner Layer 收敛成结构化动作和结构化输出

这一阶段我不想写一大堆 `if-else` 去枚举用户话术，而是先收敛系统下一步可以做的动作。

当时形成的动作集合是：

1. `reply_only`
2. `ask_clarification`
3. `update_goal`
4. `set_selection_context`
5. `create_retrieval_request`
6. `inspect_candidates`
7. `apply_patch`
8. `render_preview`

随后我又继续往前推进，固定了：

1. `planner output schema`
2. `ActionContextPacket`
3. `Context Assembler`
4. `Execution Loop`

这一步的重要性在于：

`agent` 不再只是“有状态、有工具”，而是开始拥有“状态 -> 上下文 -> 决议 -> 执行 -> 回写”的完整闭环骨架。

### 4.3 我把 Tool Layer 的理念也一起打稳了

最早我把工具层先收敛成 5 类高层工具：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

我刻意没有把底层 `ffmpeg`、向量检索、多模态问答直接暴露给 `planner`，而是把它们降到工具内部实现。

这一步是为了保护后续分层边界：

1. `planner-facing tools（面向规划器的工具）` 应保持高层语义
2. `execution backend capabilities（执行后端能力）` 可以逐步替换

### 4.4 我一度把这些骨架继续推进到了前端可运行代码

这一阶段还做过几件更偏实现的事：

1. 在前端接入 `session runtime state`
2. 代码化 `Context Assembler`
3. 代码化 `PlannerOutput`
4. 代码化 `ExecutionLoop`
5. 接入第一版启发式 `planner`
6. 再接第一版 `LLM planner`

这批工作把 `agent runtime` 从纯文档推进到了：

`至少在前端侧已经有可运行骨架的状态。`

对应主日志：

1. [2026-03-13_agent_runtime_landing_journal.md](./2026-03-13_agent_runtime_landing_journal.md)

---

## 5. 第五阶段：我继续把 retrieve / inspect / server gateway 往真实方向推进，但也在这里撞到了新的边界

这部分是目前最容易让人“跟不上”的地方，因为它同时牵涉了：

1. `agent runtime` 的工具层设计
2. `server` 的接口设计
3. `core` 的真实 `chat` 主链

### 5.1 我先重新设计了 retrieve / inspect 的理念

我后来对 `retrieve / inspect` 的理解发生过一次很关键的收缩。

我越来越认同一个原则：

`把脚手架收缩到基础设施层，把决策自由留给模型。`

也就是说：

1. 不要试图用工程师预设的一堆复杂规则“教 AI 怎么剪”
2. 应该给模型目标、上下文、工具、错误语义
3. 让模型自己决定何时搜索、何时深看、何时开始编排

基于这个原则，我后来把 `retrieve phase 1` 收紧成：

1. 主召回只使用多模态融合 `embedding`
2. 暂不把 `ASR/OCR` 作为默认辅助通道并入排序
3. `query` 来自 `retrieval hypothesis（检索假设）`，不是机械复用用户原话

同时我把 `inspect` 重新理解成：

1. 不做“开放式看图描述”
2. 而是做“假设驱动的问题式视觉判定”
3. 支持 `verify / compare / choose / rank`

这批收口最后沉淀成了：

1. [docs/agent_runtime/07_retrieval_request_schema.md](../agent_runtime/07_retrieval_request_schema.md)
2. [docs/agent_runtime/07a_retrieve_execution_design.md](../agent_runtime/07a_retrieve_execution_design.md)
3. [docs/agent_runtime/08_inspect_tool_contract.md](../agent_runtime/08_inspect_tool_contract.md)
4. [docs/agent_runtime/08a_inspect_query_prompt_contract.md](../agent_runtime/08a_inspect_query_prompt_contract.md)
5. [docs/agent_runtime/08b_inspect_execution_design.md](../agent_runtime/08b_inspect_execution_design.md)

### 5.2 我把 server 侧也按这个方向重设计了一遍

随后我开始正视一个现实问题：

阿里云 `embedding`、`DashVector`、`Gemini` 等都不应该被 `core` 直接持有，而必须经由云端 `server` 中转。

于是后来 `server` 的设计被继续收口成：

1. `planner` 继续走 `/v1/chat/completions`
2. `retrieve` 走 `/v1/assets/vectorize` 和 `/v1/assets/retrieval`
3. `inspect` 走专用 `/v1/tools/inspect`
4. `Core` 负责媒体、本地状态和未来的预览
5. `Server` 负责云端模型与向量服务网关

而且 `inspect` 还经历了一次方案切换：

1. 最早考虑过单张拼接图
2. 后来改成一次性发送多张按时间顺序排列的关键帧，并附 `timestamp` 与 `clip_duration_ms`

这批文档主要落在：

1. [docs/server/06a_server_retrieve_inspect_gateway_design.md](../server/06a_server_retrieve_inspect_gateway_design.md)
2. [docs/server/06b_server_vectorize_contract.md](../server/06b_server_vectorize_contract.md)
3. [docs/server/06c_server_retrieval_contract.md](../server/06c_server_retrieval_contract.md)
4. [docs/server/06d_server_inspect_contract.md](../server/06d_server_inspect_contract.md)
5. [docs/server/06e_server_inspect_implementation_draft.md](../server/06e_server_inspect_implementation_draft.md)

### 5.3 我还把 server 的接口实现往前推了一步

这一轮不只是写文档，`server` 端也已经被推进到了更真实的程度：

1. `/v1/assets/vectorize`
2. `/v1/assets/retrieval`
3. `/v1/tools/inspect`

这些接口都已经有实现级代码和测试，而不是只有契约。

也就是说：

`server` 这边已经从“纯设计”进入“可联调、可测试”的状态。

---

## 6. 当前真正的暂停点：我发现 core /chat 的主链方向有问题，必须先停下来收口

这次回顾里最值得强调的，不是“做了多少”，而是“我现在为什么停下来”。

问题出在 `core /api/v1/projects/{project_id}/chat`。

前一轮继续往 `Core -> Server` 联调时，`core/server.py` 一度变成了：

1. 用户输入进入 `/chat`
2. `core` 直接拿用户输入做 prompt
3. 直接跑 `vectorize / retrieval / inspect`
4. 再把结果塞回 `EditDraft`

这个方向当时虽然能更快打通工具链，但后来很明显暴露出一个原则性问题：

`工具调用是 agent 的决策，不是用户输入的直接副作用。`

换句话说，当时的 `core/chat` 其实绕过了 `plan layer（规划层）`。

这和前面已经反复确认过的 `agent runtime` 骨架是冲突的。

所以现在最新的本地改动，其实不是“再往前推进功能”，而是在纠偏：

1. `chat` 主链先进入 `planner-first` 骨架
2. 先组织上下文
3. 先调 `server /v1/chat/completions`
4. 先拿到结构化 `planner decision`
5. 真正的 `tool execution loop` 先不偷跑，而是明确打上 `TODO` 边界
6. 同时通过 `WebSocket` 暴露 `agent.step.updated`

当前这个状态非常重要，因为它意味着：

1. 系统方向被纠正了
2. 但真实 `planner -> tool execution -> replanning` 的 `core` 主循环还没有完成

也就是说，项目现在停在一个很明确的位置：

`不是工具链没想清楚，而是核心 chat 主链必须先按正确的 agent 结构收口，然后才能继续实现真实循环。`

---

## 7. 我现在对项目状态的压缩判断

如果只用几句话总结当前项目到了哪里，我会这样说：

1. 最小 `Launchpad -> Workspace -> import -> chat -> export -> preview` 闭环早就已经跑通过
2. 剪辑结构层已经从 `Storyboard` 升级为 `EditDraft`
3. `editing agent` 的五层运行时骨架已经完整讨论过，并且大部分已经文档化
4. `retrieve / inspect / patch / preview` 的工具边界已经基本形成
5. `server` 侧的 `planner / vectorize / retrieval / inspect` 契约已经成型，且部分实现和测试已经存在
6. 当前最大的收口点不在文档，而在 `core /chat` 主链是否真正按 `planner -> tool -> replanning` 的结构运行

换句话说：

`系统已经不是“想法不清”，而是进入了“主架构正确，但核心 agent loop 还没真正落地”的阶段。`

---

## 8. 我认为现在最应该记住的几件事

如果未来的我很久没碰这个项目，只需要先记住下面这些事实：

1. 当前系统的真实剪辑事实源是 `EditDraft`，不是 `Storyboard`
2. `shot` 是最小可编辑语义单元，`scene` 是可选工作分组
3. `editing agent` 应按五层理解：
   - `State`
   - `Planner`
   - `Tool`
   - `Memory / Context`
   - `Execution Loop`
4. `retrieve phase 1` 目前只走纯多模态 `embedding` 主召回，不上默认辅助通道
5. `inspect` 当前是问题驱动的视觉判定工具，不是开放式视频理解
6. `server` 的角色是云端能力网关，不是媒体处理中心
7. 当前最关键的未完成项，是 `core /chat` 的真实 `planner -> tool -> replan` 循环

---

## 9. 我现在的明确结论

这次重新回顾之后，我反而更确定一点：

这个项目最难的部分从来不是“写几个向量检索接口”，也不是“接一个多模态模型”。

真正难的，是在：

1. 保持 `agent` 自主决策的前提下
2. 不让系统退化成一堆工具拼接
3. 也不让系统退化成一个黑箱聊天机器人

而现在我认为我们已经把最关键的前置工作做完了：

1. 世界模型基本稳定
2. 工具边界基本稳定
3. 运行时骨架基本稳定
4. `server` 网关方向基本稳定

所以接下来真正的重点，不应该再分散到新的概念扩张上，而应该聚焦：

`把 core /chat 的 planner-first 骨架继续收口成真实 agent loop。`

