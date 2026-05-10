# Agent "提问机制" (AskUserQuestion) 发散设计

## 0. 为什么需要这个功能？

### 第一性原理分析

EntroCut Agent 的核心职责是「把自然语言剪辑意图转成结构化剪辑动作」。但这里有个根本矛盾：

**Agent 拥有工具和计算能力（能读、能搜、能观察、能改、能预览），但缺乏用户的品味（taste）。**

在视频剪辑中，大量决策是主观的：
- "这两段素材哪个更适合开场？" → 需要用户的审美判断
- "你想要什么情绪基调？激昂还是沉稳？" → 需要用户明确意图
- "我觉得这段画面有点暗，需要调色吗？" → 需要用户授权
- "找到了 5 个候选片段，你觉得哪个方向合适？" → 需要用户筛选

当前系统只有两个终点：调用工具继续推进，或给用户 `final` 回复。Agent 无法在「不确定」时主动向用户寻求意见，只能猜着往前走。这会导致：
1. Agent 选错方向，浪费大量 token 和工具调用
2. 用户在 final 回复看到不满意结果，推倒重来
3. Agent 的「迭代收敛」缺乏人类的 steering 作用

### 类比 Claude Code 的 AskUserQuestion

Claude Code 的 AskUserQuestion 是一个工具（tool），模型在需要人类决策时调用。但 Claude Code 的架构是请求-响应的（每次 tool call 后等待用户输入）。EntroCut 的 Agent loop 是异步推进的（后台任务），需要不同的架构处理。

### 当前架构已为此预留空间

`contracts/__init__.py` 中已经定义了：
- `ExecutionAgentRunState = Literal["idle", "planning", "executing_tool", "waiting_user", "failed"]`
  — `"waiting_user"` 从未被使用，但它就在那里
- `ConversationState.pending_questions: list[str]` — 已定义但从未填充

这表明项目的原始设计就已经预见到 Agent 需要「等待用户输入」的状态。

---

## 1. 设计决策

### 1.1 核心决策：作为 PlannerDecision 的第三种状态，而非新工具

```
PlannerDecisionStatus 从两种扩展为三种：
  final          — "我已经完成了，这是我的回复"
  requires_tool  — "我需要调用一个工具获取信息/执行动作"
  ask_user       — "我需要向用户提问，等待用户决策后再继续"
```

**为什么不是新工具？**

如果把 `ask_user` 做成一个工具，Agent 调用它后会等待用户输入作为"工具输出"。但当前 Agent loop 是 fire-and-forget 异步任务，没有暂停/恢复机制。做成工具需要大幅改造循环结构。

做成第三种决策状态的好处：
1. 与 `final` 对称 — 都是"本轮需要停止循环"的状态
2. 不需要改变工具调度和执行的代码路径
3. 状态（draft、observations、runtime_state）已经持久化在 record 中，重新发起 chat 时自动恢复

### 1.2 工作流设计

```
用户: "帮我做一个旅行视频的开场"
  → Agent 循环 1: retrieve("travel opening scenic") → 获得 5 个候选片段
  → Agent 循环 2: inspect(candidate_1) → "航拍山景，光线柔和，节奏慢"
  → Agent 循环 3: inspect(candidate_2) → "手持跟拍，动感强，色彩饱和"
  → Agent 循环 4: status = "ask_user"
      question: "你觉得开场用哪种画面风格？"
      options: ["candidate_1：开阔风景、慢节奏", "candidate_2：动感跟拍、快节奏", "两个都要，先慢后快", "让我自己输入想法"]
  → Loop 暂停，返回 AskUserResult
  → agent_run_state 设为 "waiting_user"
  → 前端弹出提问对话框
  → 用户选择 "candidate_2：动感跟拍、快节奏"
  → 用户的选择作为新的 chat 请求发送
  → 新的 Agent loop 启动，在 chat_history 中看到 Q&A
  → Agent 继续: patch(insert candidate_2) → preview → final
```

### 1.3 状态转换

```
[planning] → [executing_tool] → [planning] → ... → [final] → [idle]
                                                              ↓
                                    [planning] → ... → [ask_user] → [waiting_user]
                                                                      ↓ (用户回答)
                                                             [planning] → ...
```

---

## 2. 数据模型设计

### 2.1 新增类型

```python
# PlannerDecisionStatus 扩展
PlannerDecisionStatus = Literal["final", "requires_tool", "ask_user"]

# 提问模型
class AgentQuestionModel(BaseModel):
    """Agent 向用户提出的结构化问题"""
    id: str
    question: str = Field(min_length=1)           # 问题文本
    options: list[AgentQuestionOptionModel]       # 2-4 个选项
    allow_custom: bool = True                     # 是否允许用户自定义回答
    context_brief: str | None = None              # 简短背景说明（为什么问这个）

class AgentQuestionOptionModel(BaseModel):
    """问题选项"""
    id: str                                       # 简短 ID（如 "candidate_1"）
    label: str                                    # 显示文字（如 "开阔风景、慢节奏"）
    description: str | None = None                # 补充说明
```

### 2.2 PlannerDecisionModel 扩展

```python
class PlannerDecisionModel(BaseModel):
    status: PlannerDecisionStatus          # 新增 "ask_user"
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    assistant_reply: str | None = None     # final 状态时使用
    question: AgentQuestionModel | None = None  # ask_user 状态时使用
    current_focus: PlannerFocusModel
```

### 2.3 新增对话 Turn（用于 chat_turns 持久化）

当 Agent 问问题和用户回答时，需要在对话历史中记录，这样下一轮 Agent loop 能看到 Q&A 上下文。

```python
class AgentAskTurnModel(BaseModel):
    """Agent 提问轮次（存入 chat_turns）"""
    id: str
    role: Literal["assistant"]
    type: Literal["question"]                    # 新类型
    question: str
    options: list[dict[str, Any]]                # 选项快照
    context_brief: str | None = None

class UserAnswerTurnModel(BaseModel):
    """用户回答轮次（存入 chat_turns）"""
    id: str
    role: Literal["user"]
    type: Literal["answer"]                      # 区别于普通 user prompt
    question_id: str                             # 关联的问题 ID
    selected_option_id: str | None = None        # 选中选项
    custom_answer: str | None = None             # 或自定义文本
```

---

## 3. 上下文编排变化

### 3.1 Prompt 更新

`render_static_agent_prompt()` 新增一条决策原则：

```
11. 当你遇到需要用户品味判断、意图澄清或方向选择时，
    使用 ask_user 状态。向用户提出一个明确的问题，并给出
    2-4 个具体选项。
```

### 3.2 Output Contract 更新

`render_strict_json_output_contract()` 新增 `ask_user` 状态说明：

```
status 为 "ask_user" 时：
  - tool_name 和 tool_input 必须为 null
  - assistant_reply 必须为 null
  - question 必须包含：
      question: 用中文提出的明确问题
      options: 2-4 个选项，每个包含 id/label/description
      allow_custom: 是否允许自定义回答
      context_brief: 简短说明当前上下文和目标
  - current_focus 照常必填
```

### 3.3 对话历史渲染更新

`render_chat_history()` 需要在看到 `type == "question"` 的 turn 时渲染 Q&A：

```
Assistant: [question] 你觉得开场用什么风格？
User: [answer] candidate_2：动感跟拍、快节奏
```

---

## 4. Agent Loop 实现变更

### 4.1 `_run_chat_agent_loop` 新增 ask_user 分支

```python
# 在验证后，终止检查前
if validated.status == "ask_user":
    # 设置等待用户状态
    runtime_state_update = {
        "execution_state": {
            "agent_run_state": "waiting_user",
            ...,
        },
    }
    _apply_runtime_state_update(current_runtime_state, runtime_state_update)

    # 返回 ask_user 结果
    return AgentLoopResultModel(
        final_decision=validated,
        draft=current_draft,
        observations=observations,
        runtime_state=current_runtime_state,
        agent_steps=agent_steps,
    )
```

### 4.2 `_run_chat` 处理 ask_user 结果

在 `store.py` 的 `_run_chat` 中，循环结束后检查结果类型：

```python
if decision.status == "ask_user":
    # 创建 AgentAskTurn 存入 chat_turns
    ask_turn = AgentAskTurnModel(
        id=_entity_id("turn"),
        role="assistant",
        type="question",
        question=decision.question.question,
        options=[o.model_dump() for o in decision.question.options],
        context_brief=decision.question.context_brief,
    )
    record["chat_turns"].append(ask_turn.model_dump())

    # 执行状态设为 waiting_user（不置为 idle）
    record["runtime_state"]["execution_state"]["agent_run_state"] = "waiting_user"

    # 发出提问事件
    await store.emit(project_id, "agent.question.created", {
        "question": decision.question.model_dump(),
    })

    # Task 状态设为 paused（而非 succeeded）
    task.status = "paused"

    # 不发送 assistant_reply turns（因为 Agent 在等待，不是在回复）
```

### 4.3 用户回答后的恢复

用户通过前端的回答触发新的 chat 请求。前端将选中的选项（或自定义文本）打包为 prompt 发送。

```python
# 用户可以点选选项或输入自定义文本
# 前端将用户的选择打包为 prompt 发送（如 "@answer: candidate_2" 或直接传选项文本）
# 或者新增专用 API 端点
```

两种恢复方式：

**方式 A：复用 chat API（推荐，更简单）**
- 前端以用户的回答文案作为 prompt 调用 `POST /api/v1/projects/{id}/chat`
- Agent 在新循环中从 chat_history 看到 Q&A，继续推进
- 不需要新增 API 端点

**方式 B：专用回答 API**
- 新增 `POST /api/v1/projects/{id}/chat/answer`
- 专门接收 question_id + selected_option_id + custom_answer
- 创建 UserAnswerTurn 存入 chat_turns
- 然后启动 Agent loop

推荐方式 A，因为它最小化 API 表面积变化，且 Agent 能自然地从对话历史中理解用户的选择。

---

## 5. 前端交互设计

### 5.1 触发条件

前端监听 WebSocket 事件：
- `agent.question.created` — Agent 发出了一个新问题
- 同时 `runtime_state.execution_state.agent_run_state == "waiting_user"`

### 5.2 UI 组件：QuestionDialog

设计为聊天界面中的浮层/内联卡片（参考 Claude Code 的弹窗），内容包含：

```
┌─────────────────────────────────────────┐
│  🤔 Agent 需要你的意见                    │
│                                          │
│  context_brief (可选，灰色小字)              │
│                                          │
│  你觉得开场用哪种画面风格？                   │
│                                          │
│  ┌──────────────────────────────────┐    │
│  │ ○ 开阔风景、慢节奏                │    │
│  │   航拍山景，光线柔和，营造宁静氛围    │    │
│  ├──────────────────────────────────┤    │
│  │ ○ 动感跟拍、快节奏                │    │
│  │   手持运动，饱和度高，有活力        │    │
│  ├──────────────────────────────────┤    │
│  │ ○ 两个都要，先慢后快              │    │
│  │   开场用风景，1秒后转跟拍         │    │
│  ├──────────────────────────────────┤    │
│  │ ○ 让我自己输入想法...             │    │
│  │   [输入框：__________________]    │    │
│  └──────────────────────────────────┘    │
│                                          │
│  [提交]  [跳过/让Agent决定]               │
└─────────────────────────────────────────┘
```

### 5.3 交互流程

1. Agent 发出 `agent.question.created` 事件
2. 前端在聊天区显示 Agent 的操作步（inspect/retrieve 等），然后弹出 QuestionDialog
3. 用户的 chat 输入区域临时替换为 QuestionDialog
4. 用户选择选项或输入自定义回答后点击「提交」
5. 前端构建 prompt 文案（如「我选择 candidate_2：动感跟拍、快节奏」），调用 chat API
6. QuestionDialog 关闭，新的 Agent 循环开始
7. 对话历史中显示 "Agent 提问" 和 "用户回答" 的卡片

### 5.4 边界情况

- **用户关闭对话框**：agent_run_state 保持 `waiting_user`，用户随时可以重新回答（对话框作为聊天历史中的卡片，而非阻塞 UI）
- **用户输入新消息跳过问题**：新 chat 请求覆盖之前的 waiting 状态，Agent 在新上下文中重新开始
- **超时**：Agent 不主动超时销毁问题，由用户决定何时回应或忽略

---

## 6. 设计约束与非目标

### 6.1 必须满足的约束

1. **单向依赖**：ask_user 的模型定义在 `contracts/__init__.py`，执行逻辑在 `agent_runtime/agent.py`，不影响其他模块
2. **Prompt 紧凑性**：不暴露全量的候选片段数据给 Planner，只传递必要的上下文让 Agent 提出好问题
3. **契约先行**：`AgentQuestionModel`、`AgentAskTurnModel` 等 Schema 先定义，再实现
4. **事件驱动**：通过 WebSocket 事件通知前端，不阻塞后端
5. **可恢复**：Agent loop 暂停后，用户回答能触发新的 loop，且上下文完整

### 6.2 明确不做的事

1. 不做"Agent 在循环内暂停并恢复"（不引入 async future/await 挂起机制）
2. 不做多轮连续提问（每轮 ask_user 后必须等用户回应）
3. 不做复杂的条件分支提问（if-then 嵌套问题）
4. 不改动 Tool 接口（ask_user 不是工具，不进入 ToolCall/ToolObservation 链路）
5. 不做语音/多模态输入（只做结构化文本选项）
6. 不改变现有的 chat API 签名

---

## 7. 关键文件改动清单

| 文件 | 改动内容 |
|------|---------|
| `core/contracts/__init__.py` | 新增 `AgentQuestionModel`、`AgentQuestionOptionModel`、`AgentAskTurnModel`、`UserAnswerTurnModel`；扩展 `PlannerDecisionStatus` 加入 `"ask_user"`；更新 `ChatTurnModel` union；`PlannerDecisionModel` 新增 `question` 字段 |
| `core/application/context.py` | `render_static_agent_prompt()` 新增第 11 条决策原则；`render_strict_json_output_contract()` 新增 `ask_user` 状态的 JSON Schema 描述；`render_chat_history()` 处理 question/answer 类型 turn |
| `core/agent_runtime/agent.py` | `_run_chat_agent_loop` 新增 `ask_user` 分支（暂停循环并返回 question）；`_validate_planner_decision` 校验 question 字段合法性 |
| `core/application/store.py` | `_run_chat` 处理 `ask_user` 结果：创建 AgentAskTurn、设置 `waiting_user` 状态、发出 `agent.question.created` 事件、task 状态为 paused；用户回答后恢复 loop |
| `core/api/routers/projects.py` | chat 端点支持接收 question answer（方式 A 无变化；方式 B 新增 `chat/answer` 路由） |
| 前端 | 新增 QuestionDialog 组件；监听 `agent.question.created` 事件；连接 chat API 提交回答 |

---

## 8. 验证方案

### 8.1 单元测试

1. `AgentQuestionModel` / `PlannerDecisionModel(ask_user)` 的 schema 校验
2. `_validate_planner_decision` 正确处理 `ask_user` 状态
3. `render_chat_history` 正确渲染 question/answer 类型 turns
4. Context Assembler 正确包含 ask_user 的 JSON Schema

### 8.2 集成测试

1. 模拟 Agent 返回 `ask_user` → 验证 `agent_run_state == "waiting_user"`
2. 验证 `agent.question.created` 事件通过 WebSocket 到达前端
3. 验证用户回答后新的 Agent loop 能在 chat history 中看到 Q&A 并继续推进
4. 验证多次 ask_user 叠加不破坏状态

### 8.3 端到端

1. 启动完整三端（Client + Core + Server）
2. 创建项目、导入素材
3. 发起一个模糊的剪辑请求（如"帮我做个开场"）
4. 观察 Agent 是否在 inspect 候选片段后提出选择性问题
5. 选择答案，验证 Agent 继续推进并输出合理的 final 结果
