# Inspect Tool Contract

本文档定义 `inspect` 工具的字段级契约。

如果要看 `inspect phase 1` 的执行级设计、候选预算、证据装配与结果归一化，请继续阅读：

- [08b_inspect_execution_design.md](./08b_inspect_execution_design.md)

若要看 `inspect` 面向 `VLM（多模态大模型）` 的内部提问与返回设计，请继续阅读：

- [08a_inspect_query_prompt_contract.md](./08a_inspect_query_prompt_contract.md)

它的作用是：

`深入理解已知 clip，或对少量候选做比较、消歧、重排。`

---

## 1. 设计原则

`inspect` 只处理可定位的 `clip` 或小规模候选集，不做全量视频理解。

它必须回答：

1. 已知 `clip` 画面里有什么
2. 谁更适合
3. 为什么更适合
4. 还需不需要进一步视觉判断

本文档只回答“对外如何发起一次 inspect”，不回答“执行时内部如何展开”。后者已收敛到 [08b_inspect_execution_design.md](./08b_inspect_execution_design.md)。

---

## 2. Request

```ts
type InspectionMode = "describe" | "rank" | "compare" | "choose" | "verify";

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
  question?: string | null;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  clip_id?: string | null;
  candidates: InspectionCandidateRef[];
  require_visual_reasoning?: boolean;
  requested_at: string;
}
```

约束：

1. `describe` 需要一个明确 `clip_id`，第一版只描述一个 `clip`
2. `describe` 的 `question` 可省略，执行层会使用默认视觉描述问题
3. `verify / compare / choose / rank` 仍需要明确 `question`
4. `compare / choose / rank` 仍面向小候选集判断，不负责全量素材搜索

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
  descriptions?: Array<{
    clip_id: string;
    description: string;
    observations: string[];
    actions?: string[];
    subjects?: string[];
    scene?: string | null;
    camera?: string | null;
    editing_value?: string | null;
    uncertainty?: string | null;
  }>;
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

`inspect` 的本质，是给文本 `Agent` 一双可按需调用的眼睛：既能看懂一个已知 `clip`，也能把“召回到一堆候选”收敛成“当前最值得进入草案的少量选择”。
