# Inspect Tool Contract

本文档定义 `inspect` 工具的字段级契约。

它的作用是：

`对少量候选做比较、消歧、重排，必要时触发更深视觉判断。`

---

## 1. 设计原则

`inspect` 只处理小规模候选集，不做全量理解。

它必须回答：

1. 谁更适合
2. 为什么更适合
3. 还需不需要进一步视觉判断

---

## 2. Request

```ts
type InspectionMode = "rank" | "compare" | "choose" | "verify";

interface InspectionCandidateRef {
  clip_id: string;
  asset_id: string;
  summary: string;
  score?: number | null;
}

interface InspectToolRequest {
  project_id: string;
  session_id?: string | null;
  mode: InspectionMode;
  question: string;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  candidates: InspectionCandidateRef[];
  require_visual_reasoning?: boolean;
  requested_at: string;
}
```

---

## 3. Response

```ts
interface InspectedCandidate {
  clip_id: string;
  rank: number;
  decision_summary: string;
  confidence?: number | null;
}

interface InspectToolResponse {
  request: InspectToolRequest;
  ranked_candidates: InspectedCandidate[];
  selected_clip_id?: string | null;
  requires_more_inspection: boolean;
  responded_at: string;
}
```

---

## 4. Errors

```ts
type InspectErrorCode =
  | "NO_CANDIDATES"
  | "INSPECTION_INPUT_INVALID"
  | "VISUAL_REASONING_FAILED"
  | "DECISION_INCONCLUSIVE";

interface InspectToolError {
  code: InspectErrorCode;
  message: string;
}
```

---

## 5. 一句话结论

`inspect` 的本质，是把“召回到一堆候选”收敛成“当前最值得进入草案的少量选择”。 
