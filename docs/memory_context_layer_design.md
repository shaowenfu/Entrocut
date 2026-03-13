# Memory / Context Layer Design

本文档定义当前项目 `editing agent（剪辑智能体）` 的 `Memory / Context Layer（记忆 / 上下文层）`。

目标不是讨论“大模型怎么更聪明”，而是固定：

1. 这一层从第一性原理上在做什么
2. 为什么它是 `agent runtime（智能体运行时）` 的核心粘合层
3. 它应该由哪些工程实体构成
4. 它如何控制上下文长度、约束模型输出，并把输出映射回其它层

本文档只定义这一层的设计与边界，不展开具体模型选型、`prompt（提示词）` 文案或底层存储实现。

---

## 1. 第一性原理

任何 `agent` 都同时受到 3 个硬约束：

1. 大模型上下文窗口有限
2. 任务是多轮持续演化的
3. 执行必须基于当前最相关事实，而不是全部事实

因此，系统不可能也不应该每一轮都把以下内容全量塞给模型：

1. 全部聊天历史
2. 全部 `EditDraft`
3. 全部候选素材
4. 全部工具输出
5. 全部失败记录

但如果不保留和筛选这些信息，系统又无法持续推进任务。

所以必须有一层专门负责：

1. 保留跨轮关键事实
2. 选择当前动作真正相关的信息
3. 压缩长历史
4. 规范化工具结果
5. 把本轮新事实写回系统

一句话定义：

`Memory / Context Layer` 的本质，是把“长期任务连续性”和“单轮可决策性”接起来。

---

## 2. 它和 State Layer 的区别

很多系统失败，就是因为把 `State` 和 `Context` 混为一谈。

正确区分如下：

### 2.1 State Layer

负责：

`保存当前这次任务必须持续记住的结构化事实`

它回答的是：

1. 当前目标是什么
2. 当前草案是什么
3. 当前选区是什么
4. 当前候选和最近动作是什么

### 2.2 Memory / Context Layer

负责：

`从这些事实里，为当前一步决策拼出一份刚好够用的上下文包`

它回答的是：

1. 本轮模型现在应该看到什么
2. 哪些长历史需要被压缩
3. 哪些工具结果值得进入下一轮

所以：

1. `State` 是全量工作事实源
2. `Context` 是当前动作可见事实

两者必须分离。

---

## 3. 这一层为什么是粘合剂

五层架构里，各层职责其实很窄：

1. `State Layer`
   - 存事实
2. `Planner Layer`
   - 选下一动作
3. `Tool Layer`
   - 执行动作
4. `Execution Loop`
   - 驱动流程

但真正让系统能工作的是中间这层，因为：

1. 它从 `State` 里挑选当前相关事实
2. 它把这些事实装配给 `Planner`
3. 它把 `Tool` 结果规范化后回写
4. 它控制每轮信息量不过载

没有这层：

1. `State` 太大，模型吃不下
2. `Planner` 看不到最重要的事实
3. `Tool` 结果无法稳定进入下一轮
4. 多轮任务会越来越漂

因此它是：

`State / Planner / Tool / Loop` 之间的共享粘合层

---

## 4. 主流 agent 的共性做法

像 `Claude Code / Codex / Cursor` 这类主流 `coding agent（代码智能体）`，虽然内部细节不同，但可观察到的共性是：

1. 会话级工作记忆
   - 当前任务、已做动作、失败尝试、当前工作对象
2. 按需检索上下文
   - 根据当前动作抓最相关文件、报错、diff、测试结果
3. 工具结果规范化
   - 不直接把原始终端输出全塞回模型
4. 运行中摘要
   - 长历史被压缩成持续可用的任务摘要
5. 长期规则/记忆
   - 用户偏好、项目约定、工作规则

这套模式迁移到视频 `agent` 也是成立的。

区别只在于：

1. 代码 `agent` 检索的是文件/符号/报错
2. 视频 `agent` 检索的是 `draft/selection/candidates/preview`

所以最佳实践不是“拥有更多记忆”，而是：

`拥有更好的当前动作上下文`

---

## 5. 这一层具体在做什么

从职责上，建议拆成 4 种不同工作。

### 5.1 Working Memory（工作记忆）

保存当前会话推进真正依赖的短期工作事实。

主要来源：

1. `Session Runtime State`
2. 最近一次检索结果
3. 最近一次 patch 结果
4. 最近一次预览结果

它是这层的事实底座。

### 5.2 Context Assembly（上下文装配）

根据当前动作类型，拼出一份最小上下文包。

也就是：

1. 当前动作不同
2. 需要看到的事实不同

例如：

1. `ask_clarification`
   - 看目标缺口、约束冲突、待确认问题
2. `create_retrieval_request`
   - 看目标摘要、选区、草案局部、最近失败检索
3. `apply_patch`
   - 看草案局部、候选结果、锁定字段、当前版本

因此，这一层不是固定模板，而是：

`action-conditioned context（按动作条件化的上下文）`

### 5.3 Distillation（摘要蒸馏）

把长历史压成小而有用的摘要。

典型对象：

1. 聊天历史摘要
2. 检索历史摘要
3. patch 历史摘要
4. 用户反馈摘要

### 5.4 Write-back Normalization（回写规范化）

把本轮工具结果和模型输出提炼成可复用事实，再回写到 `runtimeState` 或缓存层。

也就是：

1. 不把原始工具输出直接回灌
2. 先抽取关键结论、证据引用、失败语义
3. 再写回系统

---

## 6. 推荐工程实体

为了避免抽象空转，这一层建议明确为 4 个工程实体。

### 6.1 Session Runtime State

这是事实源，前面已经定义。

负责：

1. 保存目标
2. 保存草案
3. 保存选区
4. 保存检索、执行、对话状态

### 6.2 Action Context Packet

这是本层最关键的对象。

它不是全量状态，而是：

`planner 在本轮真正看到的上下文对象`

建议定义为：

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

  draft_version?: number | null;
  draft_excerpt?: unknown;

  candidate_excerpt?: unknown;
  recent_failures?: string[];
  recent_actions?: string[];

  confirmed_facts?: Array<{ key: string; value: string }>;
  open_questions?: string[];

  available_tools: string[];
}
```

这里的关键不是字段全，而是：

1. 明确当前动作类型
2. 明确当前作用域
3. 明确当前版本和相关草案局部
4. 明确最近相关结果和失败

### 6.3 Context Assembler

这是本层最关键的组件。

它的输入是：

1. `Session Runtime State`
2. 当前目标动作类型
3. 可选的工具观察结果

它的输出是：

1. `ActionContextPacket`

它的职责是：

1. 按动作挑选信息
2. 控制上下文长度
3. 保证来源清晰
4. 避免过期信息进入本轮

### 6.4 Evidence Cache

用于保存可复用但不应直接放进 `runtimeState` 的证据结果。

典型内容：

1. 候选 `clip` 摘要
2. inspect 结果摘要
3. 多模态比较结果
4. 预览产物引用

它的作用是：

1. 避免重复计算
2. 在需要时向 `Context Assembler` 提供可复用证据

---

## 7. 如何控制上下文长度

控制上下文长度的原则不是“尽量短”，而是：

`只给当前动作真正需要的信息`

建议采用四级优先级裁剪。

### 7.1 第一优先级：当前动作直接依赖事实

例如：

1. 当前动作类型
2. 当前作用域
3. 当前目标摘要
4. 当前草案局部

这部分永远保留。

### 7.2 第二优先级：最近一次相关结果

例如：

1. 最近一次检索结果
2. 最近一次 inspect 结论
3. 最近一次 patch 结果

### 7.3 第三优先级：压缩后的历史摘要

例如：

1. 对话摘要
2. 历史变更摘要
3. 最近失败模式摘要

### 7.4 第四优先级：长期偏好

例如：

1. 风格偏好
2. 禁止项
3. 稳定约束

超预算时，从第四层往前裁。

因此：

1. 不默认传全量 `EditDraft`
2. 不默认传全量候选池
3. 不默认传全量聊天历史

---

## 8. 如何确定大模型输出

大模型不应该输出开放式随想，而应输出：

`受限的结构化对象`

当前建议分成两层：

### 8.1 Planner Output

先输出一个 `planner action`

例如：

1. `reply_only`
2. `ask_clarification`
3. `create_retrieval_request`
4. `apply_patch`

### 8.2 Tool-bound Payload

如果动作需要进一步执行，再产出对应契约对象：

1. `create_retrieval_request`
   - 产出 `RetrievalRequest`
2. `apply_patch`
   - 产出 `EditDraftPatch`

因此，大模型输出必须经过：

1. 动作枚举校验
2. 参数 schema 校验
3. 当前状态一致性校验

校验失败则不能直接执行。

---

## 9. 大模型输出如何映射到其它层

映射原则是：

`模型不直接修改系统，只产出结构化决策；系统负责路由和回写。`

推荐映射如下：

1. `reply_only`
   - 映射到 `Conversation State`
2. `ask_clarification`
   - 映射到 `Conversation State`
3. `update_goal`
   - 映射到 `Goal State`
4. `set_selection_context`
   - 映射到 `Selection State`
5. `create_retrieval_request`
   - 映射到 `retrieve` 工具
   - 结果回写 `Retrieval State`
6. `inspect_candidates`
   - 映射到 `inspect` 工具
   - 结果回写 `Retrieval State / Execution State`
7. `apply_patch`
   - 映射到 `patch` 工具
   - 结果回写 `Draft State / Execution State`
8. `render_preview`
   - 映射到 `preview` 工具
   - 结果回写 `Draft State / Execution State`

所以完整链路应是：

`ActionContextPacket -> LLM output -> schema validation -> router -> tool/state update -> runtimeState`

---

## 10. 最佳实践

### 10.1 State 和 Context 必须分离

`State` 保存事实，`Context` 只服务当前动作。

### 10.2 上下文必须按动作装配

不是一个固定大模板，而是多套动作模板。

### 10.3 区分四类语义

必须分开保存：

1. confirmed facts（已确认事实）
2. hypotheses（当前假设）
3. observations（工具观察）
4. failures（失败记录）

### 10.4 所有重要信息必须带来源

模型应尽量知道它看到的信息来自：

1. 用户确认
2. 当前草案
3. 检索结果
4. inspect 结果
5. 历史摘要

### 10.5 所有关键对象必须带版本

尤其是：

1. `EditDraft` 版本
2. 预览对应版本
3. 候选结果对应的检索请求

### 10.6 工具输出必须先规范化再回写

不要把原始终端输出或原始多模态描述直接塞回下一轮上下文。

### 10.7 长历史靠摘要，不靠堆叠

历史越长，越要压缩成结构化摘要。

### 10.8 上下文长度控制靠相关性，不靠盲目截断

先筛相关信息，再谈 token（上下文长度单位）预算。

---

## 11. 当前阶段的非目标

本文档明确不展开以下内容：

1. 长期跨项目记忆
2. 用户全局画像系统
3. 大规模知识库检索
4. 复杂多代理协作
5. 具体 `prompt` 模板
6. 各动作的 token 预算数值

这些不属于当前阶段的最小闭环。

---

## 12. 下一步建议顺序

基于本文档，建议后续按这个顺序落地：

1. 定义 `ActionContextPacket schema`
2. 定义 `Context Assembler` 的输入输出和裁剪规则
3. 定义工具结果的规范化摘要格式
4. 再把这些对象映射到代码里的 `planner` 调用入口

---

## 13. 一句话结论

`Memory / Context Layer` 的本质，不是“让模型记住更多”，而是：

`让模型在每一轮只看到刚好够用、来源清晰、版本正确、可执行映射的工作事实。`
