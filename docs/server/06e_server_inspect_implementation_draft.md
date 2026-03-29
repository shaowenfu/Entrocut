# Server Inspect Implementation Draft

本文档定义 `POST /v1/tools/inspect` 在 `server` 端的实现级方案。

它不再讨论“要不要做 inspect”，而是直接回答：

1. `provider mapping（提供方映射）` 怎么定
2. 上游多模态结果怎么做 `JSON normalization（JSON 归一化）`
3. 错误语义怎么稳定落到外部接口
4. 当前阶段为什么要保持成一个独立工具，而不是塞回通用 `chat/completions`

---

## 1. 当前实现结论

`inspect phase 1` 的最小稳定实现是：

1. `Core` 传入少量候选 `clip`
2. 每个候选用按时间顺序排列的关键帧序列表达
3. `Server` 把候选关键帧和判定问题发送给 `Gemini`
4. `Gemini` 必须返回单个 `JSON object（JSON 对象）`
5. `Server` 做严格解析、结构校验、语义归一化
6. 成功后返回结构化 `InspectResponse`
7. 失败时返回可枚举错误码

一句话：

`/v1/tools/inspect` 当前是“图像序列判定网关”，不是开放式对话接口，也不是视频理解引擎。`

---

## 2. Provider Mapping

### 2.1 当前 provider 选择

当前阶段只实现一个 provider：

1. `google_gemini`

原因：

1. 现有 `server` 已经具备 `Gemini` 中转能力
2. 当前还没有稳定可用的视频理解 provider
3. `inspect` 现在只需要图像级多模态判定，不需要完整视频输入

### 2.2 provider 解析规则

当前规则收敛成：

1. 若 `inspect_provider_mode == "google_gemini"`：
   - 读取 `GOOGLE_API_KEY`
   - 复用 `llm_gemini_base_url`
   - 复用 `llm_gemini_chat_path`
   - 默认模型使用 `inspect_default_model`，若为空则回退 `llm_gemini_default_model`
2. 若缺少可用配置：
   - 返回 `INSPECT_PROVIDER_UNAVAILABLE`

### 2.3 为什么不走 `/v1/chat/completions`

因为 `inspect` 不是开放式推理，而是专用工具调用。

如果走通用 `chat/completions`：

1. 候选图像会污染 `planner` 主上下文
2. `inspect` 结果难以强校验
3. 工具失败与模型失败的语义会混在一起
4. 后续无法稳定做并行、缓存与观测

所以当前原则是：

`planner` 走 `chat/completions`，`inspect` 走独立 `/v1/tools/inspect`。

---

## 3. Request Validation

`InspectRequest` 的第一层校验由 `Pydantic（数据模型校验）` 完成。

### 3.1 结构校验

必须校验：

1. `mode` 合法
2. `task_summary` 非空
3. `question` 非空
4. `candidates` 非空
5. 每个候选都有 `clip_duration_ms`
6. 每个候选至少有一帧
7. 每帧都有：
   - `frame_index`
   - `timestamp_ms`
   - `timestamp_label`
   - `image_base64`

### 3.2 语义校验

还必须校验：

1. `frames` 必须按 `timestamp_ms` 严格非降序
2. `timestamp_ms <= clip_duration_ms`
3. `verify` 只能有 1 个候选
4. `compare` 只能有 2 个候选
5. `choose` 只能有 3~5 个候选
6. `rank` 只能有 2~5 个候选

### 3.3 错误映射

1. 结构错误 -> `INVALID_INSPECT_REQUEST`
2. 证据缺失或关键帧时序非法 -> `INSPECT_EVIDENCE_MISSING`

---

## 4. Upstream Prompt Assembly

`server` 端不会把上游模型当“会自由发挥的聊天机器人”，而是把它当：

`question-driven visual judge（问题驱动的视觉判定器）`

### 4.1 固定 prompt 结构

上游请求固定包含三部分：

1. `system instruction`
   - 强约束输出为单个 `JSON object`
   - 禁止 `markdown / code fence / extra prose`
   - 明确 `mode` 语义

2. `task context`
   - `task_summary`
   - `hypothesis_summary`
   - `question`
   - `criteria`

3. `candidate evidence`
   - 按候选顺序展开
   - 每个候选带：
     - `clip_id`
     - `asset_id`
     - `clip_duration_ms`
     - `summary`
     - 多张关键帧图
   - 每张关键帧前先给一段文本锚点：
     - `frame_index`
     - `timestamp_label`
     - `timestamp_ms`

### 4.2 为什么要显式带时间锚点

因为当前没有视频模型。

要让 `Gemini` 通过多张静态图近似理解片段内容，至少必须告诉它：

1. 这些帧的先后顺序
2. 每帧在片段中的相对位置
3. 整段片长

否则它只能把这些图当成“无序图片集合”，无法较好推断片段走势。

---

## 5. JSON Parsing and Normalization

这是实现里最关键的稳定性部分。

### 5.1 上游输出要求

期望上游返回：

```json
{
  "question_type": "choose",
  "selected_clip_id": "clip_002",
  "ranking": ["clip_002", "clip_001", "clip_003"],
  "candidate_judgments": [
    {
      "clip_id": "clip_001",
      "verdict": "partial_match",
      "confidence": 0.67,
      "short_reason": "..."
    }
  ],
  "uncertainty": null
}
```

### 5.2 容错解析策略

当前建议分三步：

1. 提取 `choices[0].message.content`
2. 如果内容里有 `code fence`，先剥离
3. 从文本中提取第一个平衡的 `JSON object`

然后：

1. `json.loads`
2. 用 `InspectResponse` 做模型校验
3. 再做基于请求上下文的语义归一化

### 5.3 归一化规则

归一化必须做：

1. `question_type` 缺失时，用请求里的 `mode`
2. `ranking` 若存在，必须：
   - 元素唯一
   - 元素属于请求里的 `clip_id`
3. `selected_clip_id` 若存在，必须属于请求候选
4. `candidate_judgments[].clip_id` 必须全部属于请求候选
5. `candidate_judgments` 至少覆盖 1 个候选
6. `choose / compare` 若缺少明确选择，但 `ranking` 非空，则用 `ranking[0]` 回填 `selected_clip_id`

### 5.4 判为无效响应的条件

出现以下任一情况，应返回 `INSPECT_PROVIDER_INVALID_RESPONSE`：

1. 上游返回不是合法 JSON
2. 顶层不是对象
3. `candidate_judgments` 结构非法
4. 出现未知 `clip_id`
5. `ranking` 重复或为空但模式需要排序支撑

### 5.5 判为“无法稳定决策”的条件

以下情况建议返回 `DECISION_INCONCLUSIVE`：

1. `choose / compare` 最终仍没有可用 `selected_clip_id`
2. 上游显式给出高不确定结论，且没有稳定排序
3. 所有候选都被判断为 `mismatch`

这类情况不是 provider 崩了，而是：

`当前证据不足以得出稳定结论。`

---

## 6. Error Semantics

当前实现建议固定以下错误码：

### 6.1 `INVALID_INSPECT_REQUEST`

用于：

1. 请求体不是合法对象
2. 必填字段缺失
3. `mode` 不合法
4. 候选数与模式不匹配

HTTP 建议：

1. `422`

### 6.2 `INSPECT_EVIDENCE_MISSING`

用于：

1. 候选缺关键帧
2. 缺 `clip_duration_ms`
3. `timestamp_ms` 越界
4. 关键帧顺序错误

HTTP 建议：

1. `422`

### 6.3 `INSPECT_PROVIDER_UNAVAILABLE`

用于：

1. 未配置 `GOOGLE_API_KEY`
2. provider 超时
3. provider 网络失败
4. provider 返回 `4xx/5xx`

HTTP 建议：

1. `503` 用于本地未配置
2. `502/504` 用于上游调用失败

### 6.4 `INSPECT_PROVIDER_INVALID_RESPONSE`

用于：

1. 上游 body 无法解析
2. 上游 JSON 结构不符合契约
3. 上游返回未知 `clip_id`

HTTP 建议：

1. `502`

### 6.5 `DECISION_INCONCLUSIVE`

用于：

1. provider 可用
2. 响应结构合法
3. 但基于当前证据无法做出稳定选择

HTTP 建议：

1. `200`
2. 或 `409`

当前阶段更建议：

1. 返回 `200`
2. 在响应体内保留 `uncertainty`
3. 只有在无法形成最小可用结构时才抛异常

也就是：

`能返回结构化不确定结果，就不要把它提升成 transport error。`

---

## 7. Route-Level Behavior

`POST /v1/tools/inspect` 的最小执行顺序应固定为：

1. 鉴权
2. 请求模型校验
3. 日志记录 `inspect_started`
4. provider resolution
5. prompt assembly
6. 上游调用
7. JSON parse + normalize + validate
8. 日志记录 `inspect_succeeded`
9. 返回结构化响应

失败时：

1. 记录 `inspect_failed`
2. 使用稳定错误语义返回

---

## 8. 观测与测试重点

### 8.1 日志

建议至少记录：

1. `inspect_started`
2. `inspect_succeeded`
3. `inspect_failed`

字段至少包括：

1. `request_id`
2. `user_id`
3. `mode`
4. `candidate_count`
5. `provider`
6. `selected_clip_id`
7. `error_code`

### 8.2 指标

建议至少记录：

1. `server_inspect_requests_total{status,mode}`
2. `server_inspect_provider_latency_ms{provider,mode}`

### 8.3 最小测试矩阵

必须覆盖：

1. 未登录访问 -> `401`
2. 请求体非法 -> `422`
3. 关键帧证据缺失 -> `422`
4. provider 配置缺失 -> `503`
5. provider 返回非法 JSON -> `502`
6. provider 返回合法判断 -> `200`
7. `choose` 模式缺 `selected_clip_id` 但有 `ranking` 时可自动归一化

---

## 9. 一句话结论

`/v1/tools/inspect` 的实现重点不是“把图片发给 Gemini”，而是“把候选关键帧序列稳定地转成一个可验证、可归一化、可观测的结构化视觉判定结果”。`
