# Retrieval Request Schema

本文档定义 `retrieve` 工具的字段级契约。

它的作用是：

`把当前编辑假设，转成一个基于纯多模态 embedding 的单次候选召回请求。`

---

## 1. 设计原则

当前阶段，`retrieve` 的职责要收得很窄：

1. 只负责 `high recall（高召回）` 初筛，不负责最终选择
2. 主召回只使用候选 `clip` 的多模态融合 `embedding`
3. 不在 phase 1 中把 `ASR/OCR / tags / shot stats` 混进主排序
4. `query` 不应机械复用用户原话，而应来自 `retrieval hypothesis（检索假设）`
5. 约束只表达搜索空间边界，不承担语义替代职责

所以一个检索请求必须至少表达：

1. 当前是在补什么编排缺口
2. 当前假设想找什么镜头
3. 可接受的搜索空间边界
4. 这次要召回多少候选
5. 召回不够时是否允许改写 query 或扩展假设

---

## 2. Request

```ts
type RetrievalIntent =
  | "fill_gap"
  | "replace_shot"
  | "replace_scene"
  | "find_opening"
  | "find_transition"
  | "find_ending"
  | "gather_options";

type RetrievalQueryMode =
  | "semantic"
  | "proxy_semantic"
  | "reference_rewrite";

interface RetrievalHypothesis {
  summary: string;
  observable_proxies?: string[];
}

interface RetrievalConstraintSet {
  allowed_asset_ids?: string[];
  excluded_asset_ids?: string[];
  excluded_clip_ids?: string[];
  min_duration_ms?: number | null;
  max_duration_ms?: number | null;
}

interface RetrievalPolicy {
  top_k: number;
  allow_query_rewrite: boolean;
  allow_hypothesis_expansion: boolean;
  diversify_results: boolean;
}

interface RetrievalRequest {
  project_id: string;
  session_id?: string | null;
  intent: RetrievalIntent;
  hypothesis: RetrievalHypothesis;
  query: string;
  query_mode: RetrievalQueryMode;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  constraints?: RetrievalConstraintSet;
  policy: RetrievalPolicy;
  requested_at: string;
}
```

---

## 3. Response

```ts
interface RetrievedCandidate {
  clip_id: string;
  asset_id: string;
  summary: string;
  embedding_score: number;
  duration_ms: number;
  why_retrieved?: string | null;
  deep_inspected: boolean;
}

interface RetrievalResponse {
  request: RetrievalRequest;
  candidates: RetrievedCandidate[];
  sufficient: boolean;
  insufficiency_reason?: string | null;
  responded_at: string;
}
```

---

## 4. Errors

```ts
type RetrievalErrorCode =
  | "RETRIEVAL_INPUT_INVALID"
  | "NO_SEARCH_SPACE"
  | "RETRIEVAL_FAILED"
  | "CANDIDATES_INSUFFICIENT";

interface RetrievalError {
  code: RetrievalErrorCode;
  message: string;
  request?: Partial<RetrievalRequest>;
}
```

---

## 5. 设计说明

### 5.1 为什么不把 `ASR/OCR` 放进 phase 1 主召回

因为当前阶段最强的召回信号就是候选 `clip` 的多模态融合 `embedding`。

如果把 `ASR/OCR / tags / shot stats` 直接混入主排序：

1. 很容易污染视觉与整体语义空间
2. 检索失效时很难归因
3. 会让 `retrieve` 过早承担“精判”职责

因此 phase 1 的策略是：

`纯 embedding 主召回，辅助通道未来再增量引入。`

### 5.2 为什么 `query` 要来自 `retrieval hypothesis`

用户原话经常是抽象的，比如：

1. “更有出发感”
2. “开头高级一点”
3. “这段更像结尾”

这些话不能直接拿去做稳定召回。

所以 `planner` 必须先把它改写成一个可搜索的假设，例如：

1. “清晨整理行李”
2. “走向车站/机场”
3. “交通工具启动或移动”

然后再从假设生成 `query`。

### 5.3 为什么约束只保留搜索空间边界

当前 `retrieve` 的职责是“先找可能有用的候选”。

所以约束应只表达：

1. 允许搜哪些素材
2. 排除哪些已用 `clip`
3. 时长边界

而不应该在 phase 1 中塞进大量“必须有某个 tag”这类语义替代条件。

---

## 6. 一句话结论

`retrieval_request` 的本质，不是多信号混合查询，而是把当前编排缺口压缩成“一个检索假设 + 一个 embedding query + 一组最小搜索边界”。 
