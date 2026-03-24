# Retrieve 执行级设计

本文档定义 `retrieve` 工具在 `phase 1` 的执行级设计。

它不再讨论“是否需要多信号混合检索”，而直接回答：

`在当前阶段，agent 应该如何用纯多模态 embedding 完成候选初筛召回。`

---

## 1. 核心结论

`retrieve` 的本质，不是“理解素材”，而是：

`用最低成本，把下一步最值得进入 inspect 的少量候选 clip 找出来。`

因此 `phase 1` 直接收敛为：

1. 检索单元固定为 `clip`
2. 主召回信号固定为每个 `clip` 的多模态融合 `embedding`
3. 查询输入固定为 `planner` 基于当前编排缺口生成的 `retrieval hypothesis`
4. `retrieve` 只做高召回初筛，不做最终选择
5. `ASR/OCR / tags / shot stats` 不进入默认主链

---

## 2. Non-goals

当前文档明确不做：

1. 不做多信号混排
2. 不做 `ASR/OCR` 辅助通道
3. 不做规则库驱动的影视语法检索
4. 不做 `inspect` 级别的视觉精判
5. 不做最终镜头编排

这些都不是 `retrieve phase 1` 的职责。

---

## 3. 第一性原理

一个真正工作的剪辑师不会先把所有素材仔细看完，再开始剪。

他做的是：

1. 先明确当前在补什么编排缺口
2. 脑中形成几个“可能有用的镜头假设”
3. 快速扫一遍素材，找出一批可能相关的候选
4. 再对小批候选仔细看

因此 `retrieve` 不应该模拟“完整理解”，而应该模拟：

`快速扫素材并圈出值得细看的候选。`

这决定了它的执行策略必须偏：

1. 低成本
2. 高召回
3. 可扩召
4. 可快速进入下一步 `inspect`

---

## 4. 角色边界

### 4.1 `planner` 负责什么

`planner` 负责回答：

1. 当前在补什么缺口
2. 想找什么类型的镜头
3. 这一轮允许搜索哪些素材
4. 这次大概要召回多少候选

它输出的是：

1. `retrieval hypothesis`
2. 单次 `query`
3. 搜索空间边界
4. 召回策略

### 4.2 `retrieve` 负责什么

`retrieve` 负责回答：

1. 在允许搜索的 `clip` 空间里，哪些候选最可能相关
2. 候选是否足够进入 `inspect`
3. 如果不够，当前失败更像是“无结果”还是“结果太弱”

### 4.3 `inspect` 负责什么

`inspect` 才负责：

1. 深看候选
2. 比较候选
3. 判定哪个最适合进入草案

所以三者分工是：

1. `planner` 决定找什么
2. `retrieve` 找出可能相关的候选
3. `inspect` 从候选里选得准

---

## 5. 检索对象与索引对象

### 5.1 检索对象

`phase 1` 固定为 `clip`。

原因：

1. `shot` 是草案使用单元，不适合做全局素材搜索
2. `asset` 太粗
3. `frame` 太细，召回结果难直接进入编排

所以：

`retrieve` 的输入空间 = 当前项目可访问的所有 `clip`。

### 5.2 每个 `clip` 最小索引载荷

当前阶段，每个 `clip` 只需要这些字段：

```ts
interface RetrieveIndexedClip {
  clip_id: string;
  asset_id: string;
  source_start_ms: number;
  source_end_ms: number;
  duration_ms: number;
  embedding_ref: string;
  thumbnail_ref?: string | null;
  frame_refs?: string[];
}
```

说明：

1. `embedding_ref` 指向向量库中的主向量
2. `thumbnail_ref / frame_refs` 是为了后续 `inspect` 取证
3. 当前不要求 `ASR/OCR / tags / stats` 进入默认检索索引

---

## 6. 输入契约如何落到执行

`retrieve` 的外部输入仍然是 [07_retrieval_request_schema.md](./07_retrieval_request_schema.md)。

但执行时要进一步展开成一个内部计划：

```ts
interface RetrieveExecutionPlan {
  request_id: string;
  project_id: string;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  query: string;
  hypothesis_summary: string;
  search_space: {
    allowed_asset_ids?: string[];
    excluded_asset_ids?: string[];
    excluded_clip_ids?: string[];
    min_duration_ms?: number | null;
    max_duration_ms?: number | null;
  };
  top_k: number;
  diversify_results: boolean;
}
```

这里最关键的是：

1. 执行阶段仍只跑一个主 `query`
2. 不在 `phase 1` 做复杂 query 编排树
3. `phase 1` 不对外暴露 `query rewrite / hypothesis expansion` 这类执行策略字段

---

## 7. Query 生成原则

`retrieve` 不负责生成 `query`，但执行级设计必须约束什么样的 `query` 才适合进入召回。

### 7.1 正确输入

正确的 `query` 应该来自：

`当前编排缺口 -> retrieval hypothesis -> 可搜索自然语言`

例如：

1. “旅行视频开头更有出发感”
2. `planner` 生成假设：“清晨整理行李，准备出发”
3. 最终 `query`：“morning packing luggage preparing to leave”

### 7.2 错误输入

以下内容不适合作为直接 `query`：

1. 用户原话中的抽象评价
2. 长段需求原文
3. 草案结构描述
4. 规则表达式

例如：

1. “更高级一点”
2. “像电影一样”
3. “把第二段改成更有感觉”

这些都必须先被 `planner` 改写成可观察代理。

### 7.3 phase 1 约束

为了控制复杂度，`phase 1` 固定：

1. 单次请求只使用一个主 `query`
2. `query` 是文本
3. `query` 由 `planner` 负责改写
4. `retrieve` 不二次解释用户意图

---

## 8. 执行流程

### 8.1 Step 1：Resolve Search Space

根据请求里的边界条件，先确定这次允许搜哪些 `clip`。

只做这些事情：

1. 过滤允许的 `asset`
2. 排除不允许的 `asset`
3. 排除已经明确禁用的 `clip`
4. 过滤时长边界

不做这些事情：

1. 不按语义标签过滤
2. 不按 `ASR/OCR` 过滤
3. 不按镜头统计特征过滤

### 8.2 Step 2：Embed Query

将 `query` 文本编码成与 `clip` 主索引同空间的查询向量。

当前阶段固定：

1. `query` 是文本
2. 使用与入库时兼容的多模态 `embedding` 模型生成查询向量
3. 输出维度必须与索引维度一致

### 8.3 Step 3：Primary Recall

在 `DashVector` 中执行一次主召回：

1. 输入查询向量
2. 在上一步得到的搜索空间内检索
3. 返回 `top_k` 个最高相似度 `clip`

当前阶段不做：

1. 多 query 合并
2. 稀疏检索融合
3. 二次 rerank

### 8.4 Step 4：Candidate Normalization

把底层返回结果规范化成统一候选对象：

```ts
interface RetrievedCandidate {
  clip_id: string;
  asset_id: string;
  duration_ms: number;
  embedding_score: number;
  summary: string;
  why_retrieved?: string | null;
  deep_inspected: false;
}
```

其中：

1. `summary` 不是 `retrieve` 现看现写
2. 它应该来自索引中已有的简短描述或可回填展示字段
3. `why_retrieved` 只做最小解释，例如“matched primary semantic query”

### 8.5 Step 5：Near-duplicate Suppression

这是当前阶段唯一建议保留的召回后处理。

原因：

如果素材切分较细，很容易召回一串来自同一 `asset`、时间上高度重叠、内容几乎相同的 `clip`。

这会浪费 `inspect` 的注意力。

因此建议做一个极轻量的近重复抑制：

1. 对同一 `asset`
2. 若两个候选时间范围高度重叠或明显相邻
3. 只保留 `embedding_score` 更高者

这不是“多信号工程”，而是为了避免召回结果被切分噪声淹没。

### 8.6 Step 6：Sufficiency Check

`retrieve` 最后只做一个很轻的充分性判断：

1. 是否召回到了至少 `N` 个候选
2. 最高分是否高于最小可接受阈值

如果不满足，返回：

1. `sufficient = false`
2. `insufficiency_reason`

但不在当前阶段自动扩召。

自动扩召是后续能力，不是 `phase 1` 默认流程。

---

## 9. 返回契约

推荐最终返回：

```ts
interface RetrievalResponse {
  request: RetrievalRequest;
  candidates: RetrievedCandidate[];
  sufficient: boolean;
  insufficiency_reason?: "no_search_space" | "no_matches" | "weak_matches" | null;
  responded_at: string;
}
```

这里的核心是：

1. `retrieve` 返回的是候选池，不是推荐答案
2. `retrieve` 返回的是“足不足以进入 inspect”，不是“够不够直接进草案”

---

## 10. 错误语义

当前阶段建议只保留这几类错误：

```ts
type RetrievalErrorCode =
  | "RETRIEVAL_INPUT_INVALID"
  | "NO_SEARCH_SPACE"
  | "QUERY_EMBEDDING_FAILED"
  | "VECTOR_QUERY_FAILED"
  | "CANDIDATES_INSUFFICIENT";
```

说明：

1. `RETRIEVAL_INPUT_INVALID`
   - 输入缺字段或字段非法
2. `NO_SEARCH_SPACE`
   - 搜索空间被边界条件过滤为空
3. `QUERY_EMBEDDING_FAILED`
   - 查询向量生成失败
4. `VECTOR_QUERY_FAILED`
   - 向量库查询失败
5. `CANDIDATES_INSUFFICIENT`
   - 查询成功但候选太少或太弱

---

## 11. 为什么当前不做多信号

不是因为多信号永远没价值，而是因为当前阶段最重要的是：

1. 先把主召回语义空间跑通
2. 先让失败可归因
3. 先让 `planner -> retrieve -> inspect` 链路收敛

如果现在就把 `ASR/OCR / tags / shot stats` 混入主召回：

1. 很容易污染语义空间
2. 失败时无法判断问题出在 `query`、`embedding` 还是融合策略
3. 会让 `retrieve` 提前承担精判职责

所以当前策略是：

`先把单通道纯 embedding 主召回跑通，再考虑是否逐步接辅助通道。`

---

## 12. 与后续阶段的兼容方式

未来如果要加辅助通道，应以增量方式进入：

1. 先保持当前主向量召回不变
2. 将 `ASR/OCR` 设计成按需启用的辅助搜索通道
3. 只在明确依赖对白、字幕、画面文字的 query 下启用
4. 不破坏当前 `retrieval request` 主契约

也就是说：

`phase 1` 的设计不是死路，而是为后续扩展保留了稳定主干。

---

## 13. 一句话结论

`retrieve phase 1` 的正确执行设计，是：基于 `planner` 生成的单个检索假设和单个主 query，在 `clip` 级多模态融合 embedding 空间中做一次受边界约束的高召回搜索，再做最小近重复抑制和充分性判断，把候选池交给 `inspect`。
