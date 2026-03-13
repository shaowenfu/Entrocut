# Planner Output Schema

本文档定义当前项目 `editing agent（剪辑智能体）` 的 `planner output schema（规划层输出结构）`。

目标不是约束模型“怎么想”，而是固定：

1. `Planner Layer（规划层）` 对外的唯一稳定输出长什么样
2. 为什么它必须是结构化决议对象，而不是自然语言
3. 它如何和 `State / Tool / Execution Loop` 对齐
4. 当前阶段推荐的最小字段级结构是什么

本文档只定义输出契约，不展开具体 `prompt（提示词）` 文案或模型调用策略。

---

## 1. 第一性原理

在当前架构里，`planner` 的唯一职责是：

`基于当前 ActionContextPacket，决定下一步系统行为。`

所以它的输出必须服务后面两件事：

1. 系统判断“这一步到底要不要执行”
2. 系统判断“这一步应该路由到状态更新还是工具调用”

如果输出仍是开放式自然语言，系统就无法稳定：

1. 校验
2. 路由
3. 执行
4. 回写

因此第一结论是：

`planner output` 必须是结构化决议对象，而不是自由文本。`

---

## 2. 它的本质是什么

`planner output` 的本质不是“回答”，而是：

`对当前上下文下下一步系统行为的结构化决议记录。`

它至少必须回答 5 个问题：

1. 现在要做什么
2. 为什么现在做这个
3. 当前是否已具备执行条件
4. 这件事需要哪些最小参数
5. 这件事作用于哪里

所以本质上，它是：

`action selection + execution readiness + action payload + routing hints`

---

## 3. 为什么必须单独设计它

如果没有 `planner output schema`，系统只会退化成三种坏形态：

### 3.1 自然语言解释

模型输出一段“我觉得应该……”

问题：

1. 无法稳定解析
2. 无法自动路由
3. 无法判断是否已可执行

### 3.2 底层工具直出

模型直接输出底层参数，比如：

1. 检索细节
2. `ffmpeg` 参数
3. 渲染命令

问题：

1. `Planner Layer` 和 `Tool Layer` 耦死
2. 分层被破坏

### 3.3 半结构化混合输出

模型同时混合：

1. 解释文本
2. 动作建议
3. 不完整参数

问题：

1. 无法稳定校验
2. 无法形成统一路由边界

所以必须有一个独立输出契约，明确：

`planner 只负责产出结构化决议，系统负责校验与执行。`

---

## 4. 设计目标

`planner output schema` 当前只服务 5 件事：

1. 把开放推理收敛成有限动作决议
2. 把 `Planner Layer` 和 `Tool Layer` 解耦
3. 让每一轮输出都可校验、可路由、可记录
4. 让状态动作和工具动作共用统一出口
5. 让后续 router（路由器）与执行闭环可以稳定实现

它不负责：

1. 暴露模型内部推理链
2. 替代 `ActionContextPacket`
3. 替代工具层契约
4. 承载底层媒体实现细节

---

## 5. 推荐最小结构

当前阶段推荐把它定义成 3 层：

1. `header`
2. `payload`
3. `meta`

---

## 6. Header

`header` 回答：

1. 现在是什么动作
2. 是否已具备执行条件
3. 为什么是这个动作

```ts
interface PlannerDecisionHeader {
  action: PlannerActionType;
  ready: boolean;
  reason: string;
}
```

设计理由：

1. `action`
   - 决定路由目标
2. `ready`
   - 决定当前是直接执行，还是先停留在对话/澄清层
3. `reason`
   - 提供可解释性、调试与回放依据

---

## 7. Payload

`payload` 回答：

`这个动作真正需要的最小参数是什么`

最佳实践不是发明新字段，而是直接对齐后续工具或状态契约。

```ts
type PlannerDecisionPayload =
  | { kind: "none" }
  | { kind: "clarification"; questions: string[] }
  | { kind: "goal_update"; changes: Record<string, unknown> }
  | {
      kind: "selection_update";
      scope: "global" | "scene" | "shot";
      scene_id?: string | null;
      shot_id?: string | null;
    }
  | { kind: "retrieval_request"; request: RetrievalRequest }
  | { kind: "candidate_inspection"; request: InspectToolRequest }
  | { kind: "edit_draft_patch"; patch: EditDraftPatch }
  | { kind: "preview_request"; request: PreviewToolRequest };
```

设计理由：

1. `reply_only`
   - 对应 `none`
2. `ask_clarification`
   - 对应 `clarification`
3. `update_goal`
   - 对应 `goal_update`
4. `set_selection_context`
   - 对应 `selection_update`
5. `create_retrieval_request`
   - 对应 `retrieval_request`
6. `inspect_candidates`
   - 对应 `candidate_inspection`
7. `apply_patch`
   - 对应 `edit_draft_patch`
8. `render_preview`
   - 对应 `preview_request`

也就是说：

`payload` 必须直接服务后续状态更新或工具调用，而不是重复造一套中间字段。

---

## 8. Meta

`meta` 回答：

1. 这一步作用于哪里
2. Router（路由器）和校验层还需要知道什么

```ts
interface PlannerDecisionMeta {
  target_scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  warnings?: string[];
}
```

设计理由：

1. 方便 router 处理状态动作和工具动作
2. 方便做状态一致性校验
3. 方便记录执行警告和不确定点

---

## 9. 完整结构

```ts
interface PlannerOutput {
  header: PlannerDecisionHeader;
  payload: PlannerDecisionPayload;
  meta: PlannerDecisionMeta;
}
```

这套结构满足当前阶段的 5 个关键要求：

1. `可验证`
2. `可路由`
3. `可扩展`
4. `可解释`
5. `不耦合到底层实现`

---

## 10. 为什么这是当前阶段最优解

### 10.1 不过度耦合

它不直接暴露底层工具细节。

### 10.2 不过度抽象

它没有引入多层级复杂状态机，只回答“下一步是什么”。

### 10.3 可同时覆盖状态动作和工具动作

不是所有动作都调工具，有些动作只更新状态。

### 10.4 它天然适合做 router 和 validator

后续执行层可以直接按：

1. `header.action`
2. `payload.kind`
3. `meta.target_scope`

做路由和校验。

---

## 11. 如何映射到其它层

推荐映射如下：

1. `reply_only`
   - 写回 `Conversation State`
2. `ask_clarification`
   - 写回 `Conversation State`
3. `update_goal`
   - 写回 `Goal State`
4. `set_selection_context`
   - 写回 `Selection State`
5. `create_retrieval_request`
   - 路由到 `retrieve`
6. `inspect_candidates`
   - 路由到 `inspect`
7. `apply_patch`
   - 路由到 `patch`
8. `render_preview`
   - 路由到 `preview`

所以执行链是：

`ActionContextPacket -> PlannerOutput -> validator/router -> state/tool update -> runtimeState`

---

## 12. 校验原则

`PlannerOutput` 在执行前必须至少经过三类校验：

1. `action` 是否在允许集合里
2. `payload.kind` 是否和 `action` 匹配
3. `meta.target_scope` 是否和当前状态一致

校验失败时，不能直接执行。

---

## 13. 当前阶段的非目标

本文档明确不展开以下内容：

1. 模型内部推理字段
2. 多动作批处理输出
3. 重试策略和回退策略
4. 复杂依赖图执行
5. Router 的具体实现

这些属于下一阶段。

---

## 14. 一句话结论

`planner output schema` 的本质，是规划层对“下一步系统行为”的结构化决议记录；它必须最少包含 `header(action + ready + reason) + payload(对齐后续契约对象) + meta(scope + routing hints)`，这样系统才能稳定校验、路由、执行并回写。`
