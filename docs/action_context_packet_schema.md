# ActionContextPacket Schema

本文档定义当前项目 `editing agent（剪辑智能体）` 的 `ActionContextPacket（动作上下文包）` 设计。

目标不是把 `runtimeState（运行时状态）` 缩写一遍，而是固定：

1. `ActionContextPacket` 的本质是什么
2. 为什么它是 `Memory / Context Layer（记忆 / 上下文层）` 的核心产物
3. 最佳实践下应当如何设计
4. 当前阶段推荐的最小结构是什么

本文档只定义结构与原则，不展开具体 `prompt（提示词）` 文案和 token（上下文长度单位）预算。

---

## 1. 第一性原理

`chat-to-cut（对话到剪辑）` 的执行不是一次性生成，而是多轮持续收敛。

这意味着每一轮大模型都必须同时面对 3 个事实：

1. 当前任务依赖之前已经形成的工作事实
2. 模型上下文窗口是有限的
3. 当前这一步通常只需要完成一个具体动作

所以系统必须回答一个更基础的问题：

`为了当前这一动作，模型最少需要知道什么？`

`ActionContextPacket` 就是这个问题的结构化答案。

一句话定义：

`ActionContextPacket` 是模型在当前这一轮、为了完成某一个具体动作而被允许看到的最小工作事实包。`

---

## 2. 它的本质是什么

如果说：

1. `Session Runtime State`
   - 是全量工作事实板
2. `ActionContextPacket`
   - 就是从这块事实板上，按当前动作裁出来的一小块最相关信息

所以它的本质不是：

1. 聊天记录
2. prompt 拼盘
3. 全量状态快照

而是：

`action-conditioned context（按动作条件化的上下文）`

也就是：

1. 当前动作不同
2. 该看的信息不同

例如：

1. `create_retrieval_request`
   - 重点看目标、选区、草案缺口、最近失败检索
2. `apply_patch`
   - 重点看草案局部、候选结果、锁定字段、当前版本
3. `ask_clarification`
   - 重点看目标缺口、冲突约束、待确认问题

---

## 3. 为什么必须单独设计它

没有 `ActionContextPacket`，系统只剩两种坏选择：

### 3.1 全量注入

把：

1. 全部 `runtimeState`
2. 全部聊天历史
3. 全部候选结果
4. 全部工具输出

都塞给模型。

结果是：

1. 上下文过载
2. 过期信息污染决策
3. 相关信息被淹没

### 3.2 极简注入

只给模型最近一句话或极少量局部信息。

结果是：

1. 任务失忆
2. 局部编辑不稳定
3. 多轮对齐能力崩溃

所以必须有第三种方式：

`按当前动作，把全量工作事实裁成一份最小决策上下文。`

这就是 `ActionContextPacket` 的必要性。

---

## 4. 最佳实践原则

### 4.1 以“当前动作”为中心，而不是以“当前页面”为中心

设计时不要问：

1. 页面上显示了什么
2. store 里有什么

要问：

`为了执行当前动作，模型必须知道什么？`

所以包的结构必须天然服务：

1. `reply_only`
2. `ask_clarification`
3. `create_retrieval_request`
4. `inspect_candidates`
5. `apply_patch`
6. `render_preview`

而不是服务 UI 布局。

---

### 4.2 分层组织，而不是平铺字段

推荐固定 6 个逻辑层次：

1. `action frame`
   - 当前动作类型与当前阶段
2. `goal frame`
   - 当前目标摘要、硬约束、最近反馈
3. `scope frame`
   - 当前作用域、当前选区、锁定字段
4. `draft frame`
   - 当前草案版本与局部片段
5. `evidence frame`
   - 当前候选、最近检索/inspect 结果、失败记录
6. `tool frame`
   - 当前允许调用的工具

这样设计的好处是：

1. 结构稳定
2. 易于裁剪
3. 易于追踪来源
4. 易于按动作模板化装配

---

### 4.3 默认局部，不默认全量

最佳实践是：

1. 默认传当前相关的 `draft excerpt（草案局部摘录）`
2. 默认传当前相关的 `candidate excerpt（候选摘录）`
3. 默认传历史摘要，而不是历史原文

不应默认传：

1. 全量 `EditDraft`
2. 全量候选池
3. 全量聊天记录

原则是：

`local excerpt first, global summary second`

---

### 4.4 区分事实、假设、观察、失败

包里的信息必须至少在语义上分清：

1. `confirmed facts`
   - 用户已确认事实
2. `hypotheses`
   - 当前系统假设
3. `observations`
   - 工具返回的观察结果
4. `failures`
   - 最近失败和不足记录

否则模型很容易把：

1. 猜测当成事实
2. 旧失败当成当前约束
3. 工具观察当成用户要求

---

### 4.5 关键对象必须带来源和版本

至少以下对象应带上 `provenance（来源）` 或 `version（版本）` 语义：

1. `goal summary`
2. `draft excerpt`
3. `candidate excerpt`
4. `recent feedback`
5. `preview ref`

尤其 `draft excerpt` 必须明确来自哪个 `draft_version`。

否则系统会围绕过期信息继续推理。

---

### 4.6 历史只以摘要进入上下文

长历史不应原样进入 `ActionContextPacket`。

历史信息进入上下文时，推荐只允许 3 种形式：

1. `recent action summaries`
2. `recent failure summaries`
3. `conversation distillation`

不要把：

1. 长聊天原文
2. 长工具输出
3. 长推理过程

直接塞进去。

---

### 4.7 包的结构必须直接服务下一步输出 schema

`ActionContextPacket` 的设计目标不是“知识更全”，而是：

`让模型更容易产出正确的下一步结构化结果`

所以：

1. 要生成 `RetrievalRequest`
   - 包里就要突出目标、选区、缺口、约束、失败检索
2. 要生成 `EditDraftPatch`
   - 包里就要突出目标对象、草案局部、候选证据、锁定字段、当前版本

也就是：

`packet should be shaped for the next schema`

---

## 5. 当前阶段推荐结构

建议当前阶段把 `ActionContextPacket` 定成以下最小骨架：

```ts
interface ActionContextPacket {
  project_id: string;
  session_id: string;

  action_type: string;
  assembled_at: string;

  task_summary: string;
  goal_summary: string;

  scope: "global" | "scene" | "shot";
  selected_scene_id?: string | null;
  selected_shot_id?: string | null;
  locked_fields?: string[];

  draft_version?: number | null;
  draft_excerpt?: unknown;

  candidate_excerpt?: unknown;
  recent_failures?: string[];
  recent_actions?: string[];

  confirmed_facts?: Array<{
    key: string;
    value: string;
  }>;
  open_questions?: string[];

  available_tools: string[];
}
```

这个结构的重点不是字段名本身，而是它遵守了以下约束：

1. 当前动作显式可见
2. 当前作用域显式可见
3. 当前版本显式可见
4. 当前草案局部显式可见
5. 当前证据和失败摘要显式可见
6. 当前可用工具显式可见

---

## 6. 各层字段分别在解决什么

### 6.1 `action_type`

回答：

`这一轮现在到底要做什么`

没有它，包就失去装配目标。

### 6.2 `task_summary / goal_summary`

回答：

`这轮动作在更大任务里为什么存在`

没有它，模型只会看到局部对象，看不到全局目标。

### 6.3 `scope / selected_scene_id / selected_shot_id / locked_fields`

回答：

`这轮动作作用在哪，以及哪些边界不能碰`

没有它，局部编辑无法稳定成立。

### 6.4 `draft_version / draft_excerpt`

回答：

`当前草案事实是什么，并且是哪个版本`

没有它，patch 和 preview 都容易围绕错误版本工作。

### 6.5 `candidate_excerpt / recent_failures / recent_actions`

回答：

`当前证据是什么，最近做过什么，哪里失败过`

没有它，系统会重复劳动和重复犯错。

### 6.6 `confirmed_facts / open_questions`

回答：

`哪些是已确认事实，哪些还需要继续澄清`

没有它，agent 很快会把未确认假设当成稳定目标。

### 6.7 `available_tools`

回答：

`这一轮现在允许调用哪些外部能力`

没有它，模型很容易输出不该在当前阶段调用的动作。

---

## 7. ActionContextPacket 的底层依赖是什么

它不是凭空生成的，底层依赖主要有 4 类：

1. `Session Runtime State`
   - 提供事实源
2. `Evidence Cache`
   - 提供候选和可复用证据
3. `action type`
   - 决定当前装配目标
4. `Context Assembler rules`
   - 决定哪些信息保留、哪些信息裁掉、哪些信息摘要化

所以它的底层不是 prompt 技巧，而是：

`runtime state + evidence + action + assembly rules`

---

## 8. 它如何连接其它层

### 8.1 和 State Layer 的关系

从 `runtimeState` 取事实。

### 8.2 和 Planner Layer 的关系

作为本轮 `planner` 的直接输入。

### 8.3 和 Tool Layer 的关系

决定当前工具调用所需的最小上下文。

### 8.4 和 Execution Loop 的关系

每一轮循环里，都是：

1. 从 `runtimeState` 装配 `ActionContextPacket`
2. 交给 `planner`
3. 生成动作或工具载荷
4. 执行后回写 `runtimeState`

也就是：

`runtimeState -> ActionContextPacket -> planner output -> tool/state update -> runtimeState`

---

## 9. 当前阶段的非目标

本文档明确不展开以下内容：

1. 各动作类型的专用 `ActionContextPacket` 子 schema
2. token 预算数值
3. 具体摘要算法
4. 多模型协作时的上下文切分
5. 长期跨项目记忆

这些属于下一阶段细化内容。

---

## 10. 一句话结论

`ActionContextPacket` 的最佳实践，不是把 `runtimeState` 缩写一遍，而是把“全量工作事实”按当前动作裁成一份最小、局部、带来源与版本、并直接服务下一步结构化输出的证据包。`
