# Retrieval Request Schema

本文档定义 `retrieve` 工具的字段级契约。

它的作用是：

`把当前编辑假设，转成一个可执行、可扩召、可回放的素材检索请求。`

---

## 1. 设计原则

一个检索请求必须同时表达：

1. 想找什么
2. 不能违反什么
3. 优先什么
4. 这次想召回多少、怎么控规模

所以不能只有一个 `query: string`。

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

interface RetrievalConstraintSet {
  allowed_asset_ids?: string[];
  excluded_asset_ids?: string[];
  must_have_tags?: string[];
  excluded_tags?: string[];
  min_duration_ms?: number | null;
  max_duration_ms?: number | null;
  visual_only?: boolean;
}

interface RetrievalPreferenceSet {
  preferred_tags?: string[];
  style_hints?: string[];
  prefer_diversity?: boolean;
  prefer_novelty?: boolean;
}

interface RetrievalPolicy {
  broad_top_k: number;
  rerank_top_k: number;
  allow_query_relaxation: boolean;
  allow_constraint_relaxation: boolean;
}

interface RetrievalRequest {
  project_id: string;
  session_id?: string | null;
  intent: RetrievalIntent;
  query: string;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  constraints?: RetrievalConstraintSet;
  preferences?: RetrievalPreferenceSet;
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
  score: number;
  duration_ms: number;
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

## 5. 一句话结论

`retrieval_request` 的本质，是把模糊编辑意图压缩成“语义查询 + 约束 + 偏好 + 召回策略”。 
