# Inspect 执行级设计

本文档定义 `inspect` 工具在 `phase 1` 的执行级设计。

它回答的问题是：

`在当前阶段，agent 应该如何把一小批候选 clip 交给“眼睛”做局部视觉判定，并把结果稳定回传给 planner。`

---

## 1. 核心结论

`inspect` 的本质，不是“理解视频”，而是：

`围绕当前检索假设，对少量候选做问题驱动的视觉判定，把“找得到”收敛成“选得准”。`

因此 `phase 1` 直接收敛为：

1. 输入对象固定为小规模候选 `clip`
2. 判定方式固定为 `verify / compare / choose / rank`
3. `inspect` 只处理局部决策，不做完整编排
4. `inspect` 返回结构化观察结果，不直接生成 `patch`
5. `inspect` 内部默认由 `VLM（多模态大模型）` 承担视觉判定

---

## 2. Non-goals

当前文档明确不做：

1. 不做全量素材理解
2. 不做大规模候选池筛选
3. 不做开放式“你看到了什么”描述
4. 不做直接草案修改
5. 不做最终创作判断闭环

这些都不是 `inspect phase 1` 的职责。

---

## 3. 第一性原理

剪辑师在粗筛完候选之后，不会立刻把素材编进时间线。

他会先做一件事：

`拿几个可能有用的候选出来，围绕当前问题仔细比一眼。`

这里“仔细比一眼”不是自由欣赏，而是带着明确问题：

1. 哪个更像开头
2. 哪个更有出发感
3. 这个候选到底有没有“整理行李”动作
4. A 和 B 哪个更适合替换当前镜头

所以 `inspect` 的第一性目标不是“更懂视频”，而是：

`把注意力集中在少量候选上，用一次局部判定减少后续决策不确定性。`

---

## 4. 角色边界

### 4.1 `planner` 负责什么

`planner` 负责决定：

1. 现在要看哪批候选
2. 当前到底在问什么问题
3. 这次要验证、比较、选择还是排序
4. 结果出来后下一步准备做什么

### 4.2 `inspect` 负责什么

`inspect` 负责：

1. 读取候选的必要视觉证据
2. 按当前问题类型组织一次视觉判定
3. 返回结构化观察结果
4. 告诉上游当前结果是否足够进入下一步

### 4.3 `patch` 负责什么

`patch` 才负责把决策写回草案。

因此三者分工是：

1. `planner` 提问题
2. `inspect` 给结构化观察
3. `planner` 再决定是否进入 `patch`

---

## 5. 输入对象与证据对象

### 5.1 输入对象

`phase 1` 固定输入为：

1. 当前任务摘要
2. 当前检索假设
3. 当前问题类型
4. 当前候选集合

候选集合中的单个元素至少应包含：

```ts
interface InspectCandidate {
  clip_id: string;
  asset_id: string;
  summary?: string | null;
  retrieval_score?: number | null;
  clip_duration_ms: number;
  frames: Array<{
    frame_index: number;
    timestamp_ms: number;
    timestamp_label: string;
    image_ref: string;
  }>;
}
```

### 5.2 证据对象

当前阶段 `inspect` 不直接看整段原视频。

默认证据对象应是：

1. 按时间顺序排列的多张关键帧图
2. 每张关键帧在片段内的位置时间
3. 片段总时长
4. 候选 `summary`

也就是：

`phase 1` 默认基于“有序关键帧 + 时间位置 + 片段总时长”做视觉判定，而不是把整段视频都喂给 `VLM`。

原因：

1. 成本更可控
2. 并行性更高
3. 返回速度更快
4. 更适合做候选比较

---

## 6. 输入契约如何落到执行

`inspect` 的外部输入仍然是 [08_inspect_tool_contract.md](./08_inspect_tool_contract.md)。

但执行时要展开成一个内部计划：

```ts
interface InspectExecutionPlan {
  request_id: string;
  project_id: string;
  mode: "verify" | "compare" | "choose" | "rank";
  task_summary: string;
  hypothesis_summary?: string | null;
  question: string;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  candidates: InspectCandidate[];
  max_candidate_count: number;
  require_visual_reasoning: boolean;
}
```

这里最关键的是：

1. `inspect` 必须是问题驱动的
2. 问题类型必须先定死
3. 候选数量必须受预算约束
4. 视觉判断是否强制启用必须显式表达

---

## 7. 候选预算

`inspect` 只在小集合上工作。

当前阶段固定预算：

1. `verify`: 1 个候选
2. `compare`: 2 个候选
3. `choose`: 3~5 个候选
4. `rank`: 最多 5 个候选

如果超出预算：

1. 优先按 `retrieval_score` 做轻量截断
2. 不在 `inspect phase 1` 内部做复杂淘汰赛
3. 让更复杂的候选压缩留给未来迭代

这里的原则很明确：

`先让一次 inspect 足够快、足够稳，而不是让它吞下大规模候选池。`

---

## 8. 执行流程

### 8.1 Step 1：Preflight Check

先验证：

1. 候选是否为空
2. `mode` 与候选数是否匹配
3. `question` 是否存在
4. 当前证据是否可用

这里直接失败的情况包括：

1. 没有候选
2. `compare` 但候选不足 2 个
3. 任一候选缺少最小关键帧证据

### 8.2 Step 2：Candidate Budgeting

若候选超过当前 `mode` 预算：

1. 按 `retrieval_score` 降序截断
2. 同时保留原始候选顺序引用，方便回放

这里的截断只是“进入 inspect 前的预算控制”，不是最终视觉排序。

### 8.3 Step 3：Evidence Resolution

为每个候选取出最少必要证据：

1. 已排序的关键帧图
2. 每帧的 `timestamp_label`
3. `clip_duration_ms`
4. 候选 `summary`

当前阶段建议：

1. 不默认回源读取整段视频
2. 不在 `inspect` 里临时做新一轮帧抽取
3. 不把多张关键帧再拼成一张图发送

### 8.4 Step 4：Prompt Assembly

将上一步候选和当前局部问题组装成内部 `VLM prompt contract`。

这一步的具体结构已由：

- [08a_inspect_query_prompt_contract.md](./08a_inspect_query_prompt_contract.md)

定义。

执行层只负责：

1. 根据 `mode` 选标准问题模板
2. 带入当前 `task_summary / hypothesis / question / candidates`
3. 要求严格结构化输出

### 8.5 Step 5：Visual Judgment

调用一次 `VLM` 完成局部视觉判定。

当前阶段建议：

1. 一个 `inspect request` 对应一次主 `VLM` 调用
2. 不在 `inspect phase 1` 内部递归多轮追问
3. 若输出不合法，最多做有限次格式修复重试

### 8.6 Step 6：Observation Normalization

将 `VLM` 输出规范化成统一观察对象：

```ts
interface InspectionObservation {
  question_type: "verify" | "compare" | "choose" | "rank";
  selected_clip_id?: string | null;
  ranking?: string[];
  candidate_judgments: Array<{
    clip_id: string;
    verdict: "match" | "partial_match" | "mismatch";
    confidence?: number | null;
    short_reason: string;
  }>;
  uncertainty?: string | null;
}
```

### 8.7 Step 7：Tool Response Mapping

最后把观察对象映射回对外 `InspectToolResponse`：

```ts
interface InspectToolResponse {
  request: InspectToolRequest;
  ranked_candidates: Array<{
    clip_id: string;
    rank: number;
    decision_summary: string;
    confidence?: number | null;
  }>;
  selected_clip_id?: string | null;
  requires_more_inspection: boolean;
  responded_at: string;
}
```

这里的映射原则是：

1. `ranking` 优先决定 `ranked_candidates`
2. `candidate_judgments` 决定每个候选的解释摘要
3. 若 `uncertainty` 明显较高，则 `requires_more_inspection = true`

---

## 9. 四种模式的执行语义

### 9.1 `verify`

作用：

验证单个候选是否满足一个明确条件。

执行特征：

1. 候选数固定为 1
2. 输出重点是 `verdict + confidence + short_reason`
3. 不强调 `ranking`

### 9.2 `compare`

作用：

比较两个候选在某个局部问题上的优劣。

执行特征：

1. 候选数固定为 2
2. 输出重点是 `selected_clip_id`
3. `ranking` 可选，但建议返回

### 9.3 `choose`

作用：

从小集合中直接选出当前最优项。

执行特征：

1. 候选数通常 3~5
2. 必须返回 `selected_clip_id`
3. 同时建议返回完整 `ranking`

### 9.4 `rank`

作用：

给候选排序，但不强制唯一选择。

执行特征：

1. 候选数最多 5
2. 核心输出是 `ranking`
3. `selected_clip_id` 可为空

---

## 10. 错误语义

当前阶段建议只保留这几类错误：

```ts
type InspectErrorCode =
  | "NO_CANDIDATES"
  | "INSPECTION_INPUT_INVALID"
  | "INSPECTION_EVIDENCE_MISSING"
  | "VISUAL_REASONING_FAILED"
  | "DECISION_INCONCLUSIVE";
```

说明：

1. `NO_CANDIDATES`
   - 没有候选可看
2. `INSPECTION_INPUT_INVALID`
   - `mode`、问题、候选数等输入不合法
3. `INSPECTION_EVIDENCE_MISSING`
   - 候选缺少足够视觉证据
4. `VISUAL_REASONING_FAILED`
   - `VLM` 调用失败或输出无法恢复
5. `DECISION_INCONCLUSIVE`
   - 看完了，但仍无法得出足够稳定的结论

---

## 11. 为什么当前不把 inspect 内化到基座模型

不是因为它永远不该内化，而是因为当前阶段保留独立工具更稳。

原因：

1. 更容易并行
2. 更容易缓存
3. 不会把主 `planner` 上下文挤爆
4. 更容易替换底层 `VLM`
5. 更容易观察和调试

所以当前原则是：

`planner` 决定要问什么，`inspect tool` 负责真正去“看”。`

未来如果基座模型足够强、足够便宜、足够稳定，再考虑把一部分视觉判断内化。

---

## 12. 与后续阶段的兼容方式

未来可以沿这条线扩：

1. 从关键帧证据扩到短视频片段证据
2. 从单次 `VLM` 调用扩到多轮判定
3. 从简单截断扩到候选淘汰赛
4. 从单一 `VLM` 扩到专门视觉 `judge`

但这些都不应破坏当前主干：

1. 小候选集
2. 问题驱动
3. 结构化输出
4. 不直接生成 `patch`

---

## 13. 一句话结论

`inspect phase 1` 的正确执行设计，是：围绕当前检索假设和局部问题，把少量候选 `clip` 的多关键帧序列、每帧时间位置和片段总时长组装成一次受模式约束的视觉判定请求，调用 `VLM` 返回结构化观察结果，再把这些观察规范化成可供 `planner` 继续决策的候选判断。
