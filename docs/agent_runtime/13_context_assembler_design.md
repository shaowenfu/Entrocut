# Context Assembler Design

本文档定义当前项目 `editing agent（剪辑智能体）` 的 `Context Assembler（上下文装配器）`。

目标不是讨论“大模型怎么提示更好”，而是固定：

1. `Context Assembler` 在系统中的本质职责是什么
2. 为什么它是 `Memory / Context Layer（记忆 / 上下文层）` 真正可执行的核心组件
3. 它的输入、输出、装配流程、裁剪规则和失败语义是什么
4. 它如何把 `runtimeState -> ActionContextPacket -> planner output` 串起来

本文档只定义设计与边界，不展开具体 `prompt（提示词）` 文案、摘要模型选型或 token（上下文长度单位）预算数值。

---

## 1. 第一性原理

如果说：

1. `Session Runtime State`
   - 保存全量工作事实
2. `ActionContextPacket`
   - 是本轮动作需要看到的最小事实包

那么中间还缺一个关键问题：

`谁来决定，当前这一轮到底该从全量事实里取哪些信息，并怎么组织成可给 planner 使用的上下文包？`

这个角色就是 `Context Assembler`。

一句话定义：

`Context Assembler` 是一个按当前动作类型，从 runtime state 和相关证据中装配最小决策上下文包的组件。`

---

## 2. 它的本质是什么

`Context Assembler` 的本质，不是“拼 prompt”，而是一个：

`context selection and shaping engine（上下文选择与整形引擎）`

它底层在做的是 4 件事：

1. 从全量工作事实中做相关性选择
2. 对长历史做摘要和压缩
3. 对工具结果做规范化和证据抽取
4. 按当前动作模板，把信息组织成统一结构

所以它不是：

1. 数据库存取层
2. 聊天记录拼接器
3. 单纯的字符串模板器

而是：

`把“全量事实”转换成“当前动作可决策输入”的运行时装配器`

---

## 3. 为什么必须单独存在

如果没有 `Context Assembler`，系统只能在两种坏方案里选一个：

### 3.1 粗暴全量注入

把：

1. 全量 `runtimeState`
2. 全量聊天
3. 全量候选
4. 全量工具输出

一股脑交给模型。

问题：

1. 上下文过长
2. 相关信息被淹没
3. 过期信息污染决策

### 3.2 手工临时拼接

每种动作都在代码里零散地 `if-else` 拼字段。

问题：

1. 难维护
2. 容易失去一致性
3. 无法形成稳定上下文规范

所以必须有第三种方式：

`把上下文选择、裁剪、摘要、装配明确沉淀成一个独立组件。`

这就是 `Context Assembler` 的必要性。

---

## 4. 它在五层架构中的位置

推荐关系如下：

1. `State Layer`
   - 提供事实源
2. `Evidence Cache`
   - 提供可复用证据
3. `Context Assembler`
   - 读取事实，装配 `ActionContextPacket`
4. `Planner Layer`
   - 基于 `ActionContextPacket` 产出结构化动作
5. `Tool Layer`
   - 执行动作
6. `Execution Loop`
   - 把结果回写，再进入下一轮

也就是：

`runtimeState + evidence -> Context Assembler -> ActionContextPacket -> planner -> tool -> runtimeState`

`Context Assembler` 是这条链里把状态变成决策输入的关键桥梁。

---

## 5. 设计目标

当前阶段，`Context Assembler` 只服务 5 件事：

1. 为当前动作生成最小充分上下文
2. 控制上下文长度
3. 保证事实来源和版本清晰
4. 隔离长历史和原始工具输出
5. 让 `planner output` 更容易对齐目标 schema（结构）

它不负责：

1. 决定下一步动作是什么
2. 直接调用工具
3. 持久化状态
4. 生成最终自然语言回复

---

## 6. 输入是什么

当前阶段建议 `Context Assembler` 的最小输入如下：

```ts
type PlannerActionType =
  | "reply_only"
  | "ask_clarification"
  | "update_goal"
  | "set_selection_context"
  | "create_retrieval_request"
  | "inspect_candidates"
  | "apply_patch"
  | "render_preview";

interface ContextAssemblyInput {
  project_id: string;
  session_id: string;
  action_type: PlannerActionType;
  runtime_state: unknown;
  evidence_refs?: {
    candidate_ids?: string[];
    preview_ref_ids?: string[];
    retrieval_request_id?: string | null;
  };
  include_recent_failures?: boolean;
  include_recent_actions?: boolean;
  assembled_at: string;
}
```

这里真正重要的输入只有 4 类：

1. 当前要服务哪个动作
2. 当前会话的 `runtimeState`
3. 哪些证据需要纳入本轮
4. 当前是否需要补历史摘要

---

## 7. 输出是什么

输出应固定为 `ActionContextPacket`。

也就是：

```ts
interface ContextAssemblyOutput {
  packet: ActionContextPacket;
  assembly_meta: {
    action_type: string;
    used_sections: string[];
    omitted_sections: string[];
    warnings: string[];
    assembled_at: string;
  };
}
```

这样设计的原因是：

1. `packet` 负责给 `planner`
2. `assembly_meta` 负责调试、可观测性和后续优化

也就是说，`Context Assembler` 不只输出上下文，还输出：

`这次上下文是怎么被装出来的`

---

## 8. 装配流程

建议把装配过程固定成 6 个阶段。

### 8.1 Resolve Action Frame（确定动作帧）

先明确：

1. 当前动作类型
2. 当前作用域
3. 当前动作最低需要哪些信息

这是整个装配流程的入口。

没有动作帧，就无法决定后续选什么信息。

---

### 8.2 Pull Required Facts（拉取必需事实）

从 `runtimeState` 里拉当前动作直接依赖的事实。

例如：

1. `create_retrieval_request`
   - 目标摘要
   - 当前作用域
   - 当前草案缺口
2. `apply_patch`
   - 当前草案局部
   - 当前版本
   - 锁定字段
3. `ask_clarification`
   - 当前开放问题
   - 缺失的目标约束

这一步只拉“必需事实”，不拉“可能有用事实”。

---

### 8.3 Pull Relevant Evidence（拉取相关证据）

从 `Evidence Cache` 或最近工具结果中拉当前动作相关证据。

例如：

1. 最近候选摘要
2. 最近 inspect 结论
3. 最近 preview 结果
4. 最近 retrieval 不足原因

这一步必须按动作取证，不能默认全拉。

---

### 8.4 Distill History（蒸馏历史）

把历史信息压缩成摘要。

当前推荐只允许进入：

1. `recent action summaries`
2. `recent failure summaries`
3. `conversation distillation`

不允许进入：

1. 全量聊天原文
2. 全量工具输出
3. 全量检索历史

---

### 8.5 Enforce Budget（执行预算裁剪）

这是上下文长度控制的关键阶段。

建议按 4 级优先级裁剪：

1. 当前动作直接依赖事实
2. 最近一次相关证据
3. 历史摘要
4. 长期偏好

超预算时从后往前裁。

原则不是“均匀截断”，而是：

`priority-based omission（按优先级丢弃）`

---

### 8.6 Assemble Packet（组装上下文包）

把保留下来的信息组织成统一 `ActionContextPacket` 结构，并附上：

1. 来源信息
2. 版本信息
3. 当前可用工具列表

到这一步才真正产出供 `planner` 使用的上下文。

---

## 9. 动作模板化规则

最佳实践不是一个统一模板，而是：

`one assembler, multiple action templates（一个装配器，多套动作模板）`

当前建议至少固定以下装配模板差异。

### 9.1 `ask_clarification`

应优先包含：

1. 当前目标缺口
2. 冲突约束
3. 开放问题
4. 最近用户反馈

应弱化：

1. 候选细节
2. 草案细节

### 9.2 `create_retrieval_request`

应优先包含：

1. 当前目标摘要
2. 当前作用域
3. 当前草案缺口
4. 最近失败检索
5. 当前检索边界和可搜范围

### 9.3 `inspect_candidates`

应优先包含：

1. 候选摘录
2. 当前比较问题
3. 当前目标摘要
4. 当前作用域

### 9.4 `apply_patch`

应优先包含：

1. 当前草案局部
2. 当前版本
3. 候选证据
4. 锁定字段
5. 目标对象标识

### 9.5 `render_preview`

应优先包含：

1. 当前草案版本
2. 当前预览范围
3. 最近 patch 变更摘要

所以 `Context Assembler` 的关键不是“能不能组包”，而是：

`能不能按动作稳定切换装配模板`

---

## 10. 如何控制上下文长度

`Context Assembler` 是上下文预算的第一责任人。

最佳实践是：

### 10.1 先做相关性筛选，再做长度裁剪

不要先拼满再砍。

正确顺序是：

1. 先按动作选信息
2. 再按优先级裁剪

### 10.2 默认局部摘录

不要默认给：

1. 全量 `EditDraft`
2. 全量候选
3. 全量历史

### 10.3 历史只进摘要

所有长历史都必须先经过摘要层。

### 10.4 低优先级信息必须可丢弃

如果某类字段无法被裁掉，说明设计过重。

---

## 11. 如何保证来源和版本不混乱

`Context Assembler` 必须保证至少两件事：

### 11.1 关键对象带版本

例如：

1. `draft_version`
2. `preview_version`
3. 候选对应的检索请求

### 11.2 关键结论带来源

例如：

1. 来自用户确认
2. 来自当前草案
3. 来自检索结果
4. 来自 inspect 判断
5. 来自历史摘要

没有这些信息，模型很容易把：

1. 旧结论当新结论
2. 假设当事实
3. 工具观察当用户要求

---

## 12. 失败语义

`Context Assembler` 也需要自己的错误语义。

当前建议最小错误集合如下：

```ts
type ContextAssemblyErrorCode =
  | "RUNTIME_STATE_MISSING"
  | "ACTION_TYPE_INVALID"
  | "REQUIRED_FACT_MISSING"
  | "EVIDENCE_REF_INVALID"
  | "ASSEMBLY_BUDGET_EXCEEDED";

interface ContextAssemblyError {
  code: ContextAssemblyErrorCode;
  message: string;
  action_type?: string;
  missing_fields?: string[];
}
```

其中：

1. `RUNTIME_STATE_MISSING`
   - 没有可装配事实源
2. `ACTION_TYPE_INVALID`
   - 无法识别动作模板
3. `REQUIRED_FACT_MISSING`
   - 当前动作关键事实缺失
4. `EVIDENCE_REF_INVALID`
   - 指向了不存在的证据
5. `ASSEMBLY_BUDGET_EXCEEDED`
   - 即使裁剪后仍超预算

---

## 13. 和其它层的关系

### 13.1 和 State Layer

读取 `runtimeState`，但不拥有状态。

### 13.2 和 ActionContextPacket

`ActionContextPacket` 是它的标准输出。

### 13.3 和 Planner Layer

`planner` 不直接读全量状态，而是读它输出的包。

### 13.4 和 Tool Layer

工具结果不会直接喂回模型，而是先进入证据层，再由它决定是否进入下一包。

### 13.5 和 Execution Loop

每轮执行闭环里，它承担的是：

`state/evidence -> current action packet`

---

## 14. 当前阶段的非目标

本文档明确不展开以下内容：

1. 具体摘要算法
2. 多模型协作时的包分发
3. 长期记忆数据库设计
4. token 预算具体阈值
5. prompt 拼装模板细节

这些属于后续实现细化。

---

## 15. 一句话结论

`Context Assembler` 的本质，是把全量工作事实按当前动作类型裁剪、摘要、规范化并装配成 `ActionContextPacket` 的运行时引擎；没有它，Memory / Context Layer 就只是概念，不是可执行系统。`
