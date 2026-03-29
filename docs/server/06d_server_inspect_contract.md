# Server Inspect Contract

本文档定义 `POST /v1/tools/inspect` 的字段级契约草案。

当前阶段，它只服务一件事：

`把少量候选 clip 的多关键帧序列、中间时间锚点和片段总时长交给图像多模态模型，返回结构化视觉判定结果。`

---

## 1. 设计边界

当前阶段：

1. 输入对象固定为小规模候选 `clip`
2. 每个候选用多张关键帧图表达
3. 每张关键帧必须带时间位置
4. 同时必须带片段总时长
5. 输出固定为结构化 `InspectionObservation`

当前不做：

1. 不上传原始视频
2. 不做长视频理解
3. 不做开放式聊天
4. 不直接生成 `EditDraftPatch`

---

## 2. Endpoint

```http
POST /v1/tools/inspect
Authorization: Bearer <jwt>
Content-Type: application/json
```

---

## 3. Request Schema

```ts
type InspectMode = "verify" | "compare" | "choose" | "rank";

interface InspectFrame {
  frame_index: number;
  timestamp_ms: number;
  timestamp_label: string;
  image_base64: string;
}

interface InspectCandidate {
  clip_id: string;
  asset_id: string;
  clip_duration_ms: number;
  summary?: string | null;
  frames: InspectFrame[];
}

interface InspectRequest {
  mode: InspectMode;
  task_summary: string;
  hypothesis_summary?: string | null;
  question: string;
  criteria?: Array<{
    name: string;
    description: string;
  }>;
  candidates: InspectCandidate[];
}
```

### 3.1 字段约束

1. `mode` 必填
2. `question` 必填
3. `candidates` 非空
4. 每个候选必须有 `clip_duration_ms`
5. 每个候选必须至少有一张关键帧
6. `frames` 必须按时间顺序排列
7. `timestamp_ms <= clip_duration_ms`

### 3.2 候选预算建议

1. `verify`: 1 个候选
2. `compare`: 2 个候选
3. `choose`: 3~5 个候选
4. `rank`: 最多 5 个候选

---

## 4. Response Schema

```ts
interface CandidateJudgment {
  clip_id: string;
  verdict: "match" | "partial_match" | "mismatch";
  confidence?: number | null;
  short_reason: string;
}

interface InspectResponse {
  question_type: InspectMode;
  selected_clip_id?: string | null;
  ranking?: string[];
  candidate_judgments: CandidateJudgment[];
  uncertainty?: string | null;
}
```

---

## 5. Errors

```ts
type InspectErrorCode =
  | "INVALID_INSPECT_REQUEST"
  | "INSPECT_EVIDENCE_MISSING"
  | "INSPECT_PROVIDER_UNAVAILABLE"
  | "INSPECT_PROVIDER_INVALID_RESPONSE"
  | "DECISION_INCONCLUSIVE";
```

推荐语义：

1. `INVALID_INSPECT_REQUEST`
   - 输入字段非法或候选数与 `mode` 不匹配
2. `INSPECT_EVIDENCE_MISSING`
   - 缺关键帧、缺时间锚点或缺总时长
3. `INSPECT_PROVIDER_UNAVAILABLE`
   - `Gemini` 或其它图像模型不可用
4. `INSPECT_PROVIDER_INVALID_RESPONSE`
   - 上游返回无法解析为结构化结果
5. `DECISION_INCONCLUSIVE`
   - 模型无法给出足够稳定的判断

---

## 6. 一句话结论

`/v1/tools/inspect` 的当前契约，本质上是“把候选 clip 的多关键帧序列和时间锚点交给图像多模态模型，换回结构化候选判断结果”的专用网关。
