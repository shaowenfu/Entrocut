# Server Inspect Contract

本文档定义 `POST /v1/tools/inspect` 的字段级契约。

当前阶段，它只服务一件事：

`接收一个 clip 的提示词和图片，调用 VLM（多模态大模型）返回图片描述。`

---

## 1. 设计边界

当前做：

1. 输入固定为一个 `clip_id`
2. 输入固定为 `prompt + image_base64`
3. 输出固定为该 `clip` 的视觉描述
4. 比较、排序、选择、剪辑决策全部交给调用方 `Agent`

当前不做：

1. 不接收候选列表
2. 不接收 `mode / criteria / ranking`
3. 不直接生成 `EditDraftPatch`
4. 不暴露 provider model 选择参数

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
interface InspectRequest {
  clip_id: string;
  prompt: string;
  image_base64: string;
}
```

字段约束：

1. `clip_id` 必填，用于把结果绑定回调用方的 `clip`
2. `prompt` 必填，由主 `Agent` 根据当前任务自行组织
3. `image_base64` 必填，当前按 `JPEG` 证据处理
4. 冗余字段必须拒绝，例如 `mode / candidates / collection_name / model`

---

## 4. Response Schema

```ts
interface InspectResponse {
  clip_id: string;
  description: string;
  uncertainty?: string | null;
  model?: string | null;
}
```

响应约束：

1. `clip_id` 必须等于请求中的 `clip_id`
2. `description` 必须是非空字符串
3. `uncertainty` 只表达视觉证据不足，不做剪辑决策
4. `model` 只用于可观测性，不由请求方指定

---

## 5. Errors

```ts
type InspectErrorCode =
  | "INVALID_INSPECT_REQUEST"
  | "INSPECT_EVIDENCE_MISSING"
  | "INSPECT_PROVIDER_UNAVAILABLE"
  | "INSPECT_PROVIDER_INVALID_RESPONSE";
```

---

## 6. 一句话结论

`/v1/tools/inspect` 是“图片描述网关”，不是“候选决策网关”。
