# Inspect Describe Mode 最小改动方案

## 1. 目标

把 `Inspect` 从 `Retrieval` 之后的候选精筛工具，提升为与 `Retrieval` 平级的视觉理解工具。

新增 `describe` mode 后，`Inspect` 的职责是：

1. 当 Agent 已经知道目标 `clip` 时，直接深入理解该 `clip`
2. 当用户显式指定某个 `clip` 时，不必先走 `Retrieval`
3. 当 Agent 对某个候选的视觉细节不确定时，用 `Inspect` 作为视觉补充
4. 由 Agent 组织任务相关的 `prompt`，服务端拼接固定 `system prompt`，调用 `VLM（多模态大模型）`

一句话边界：

`Retrieval` 负责找可能相关的 `clip`；`Inspect describe` 负责看懂已知 `clip`。

## 2. 当前实现读数

### 2.1 Server route

文件：`server/app/api/routes/inspect.py`

当前入口：

```http
POST /v1/tools/inspect
```

实现特点：

1. 使用 `InspectRequest` 作为 FastAPI request body
2. 依赖 `get_current_user`
3. 调用 `inspect_service.validate_request(...)`
4. 调用 `inspect_service.inspect(...)`
5. 日志、metrics、audit 里都使用 `payload.mode` 和 `len(payload.candidates)`

影响：

新增 `describe` 后，route 层不用拆新接口，继续复用 `/v1/tools/inspect` 即可；但日志里的 `candidate_count` 要继续兼容。

### 2.2 Server schema

文件：`server/app/schemas/inspect.py`

当前 request：

```ts
type InspectMode = "verify" | "compare" | "choose" | "rank";

interface InspectRequest {
  mode: InspectMode;
  task_summary: string;
  hypothesis_summary?: string | null;
  question: string;
  criteria?: InspectCriterion[];
  candidates: InspectCandidate[];
}
```

当前 response：

```ts
interface InspectResponse {
  question_type: InspectMode;
  selected_clip_id?: string | null;
  ranking?: string[];
  candidate_judgments: CandidateJudgment[];
  uncertainty?: string | null;
}
```

问题：

1. `Inspect` 被 Schema 固定成候选判断工具
2. `candidate_judgments` 强制非空，不适合开放描述
3. `question_type` 只允许旧 mode
4. `question` 必填，但缺少适合 `describe` 的默认 prompt 语义

### 2.3 Server service

文件：`server/app/services/inspect.py`

当前行为：

1. `_validate_semantics` 强制所有 mode 都必须有 `candidates`
2. 候选数量规则固定：
   - `verify`: 1
   - `compare`: 2
   - `choose`: 3~5
   - `rank`: 2~5
3. 每个 candidate 必须有至少一张 frame
4. `_build_upstream_payload` 使用固定 system prompt，要求 provider 只返回：
   - `question_type`
   - `selected_clip_id`
   - `ranking`
   - `candidate_judgments`
   - `uncertainty`
5. image payload 固定拼成 `data:image/jpeg;base64,...`
6. `_normalize_provider_response` 按候选判断结果做校验

问题：

`describe` 需要另一套 response 语义，但可以复用 provider 调用、frame 证据装配、JSON 解析、错误处理。

### 2.4 Core tool context

文件：`core/context.py`

当前 tool 描述：

```text
inspect purpose: 对候选进行比较、消歧与质量判断
when_to_use: 候选存在多个可行项，需要进一步判优时
when_not_to_use: 尚无候选可比较，或 retrieve 尚不可用时
```

当前 planner system prompt：

```text
For scope expansion, retrieve first; for candidate judgment, inspect.
```

问题：

这会把 Agent 强制引导成：

`先 retrieve，再 inspect`

不支持：

1. 用户指定 `clip` 后直接 inspect
2. 对单个 clip 做开放描述
3. Agent 不确定某个视觉细节时主动 inspect

### 2.5 Core inspect execution

文件：

1. `core/agent.py`
2. `core/inspection.py`

当前执行：

1. 从 `tool_input.clip_id` 或 `runtime_state.retrieval_state.candidate_clip_ids` 里选一个 clip
2. 调用本地 `inspect_candidate(...)`
3. 返回基于 `clip.visual_desc` 拼出的摘要
4. 不调用 server `/v1/tools/inspect`
5. 不支持 `mode`
6. 不支持 Agent 自定义视觉问题

问题：

即使 server 增加 `describe`，Agent 侧如果不改上下文和执行层，也不会真正使用 VLM。

## 3. 最小改动原则

本轮不做：

1. 不新增 `/v1/tools/describe` 接口
2. 不重写 `Retrieval`
3. 不把 `Inspect` 改成全量视频理解
4. 不设计复杂 `detail_level`、`focus_area`、`output_format` 参数
5. 不改变旧 `verify/compare/choose/rank` 的外部行为

本轮只做：

1. 在现有 `/v1/tools/inspect` 上新增 `mode: "describe"`
2. 为 `describe` 增加最小 Schema 与 response 兼容
3. 为 `describe` 增加独立 system prompt
4. 更新 `core` 侧 tool context，让 Agent 知道何时用 `Inspect describe`
5. 让 Agent 能把 `mode`、`clip_id`、`question` 传入 inspect 执行路径

## 4. 推荐 Schema 变化

### 4.1 Request

保留当前 `candidates` 结构，不引入新的 `clip_ids` 字段。

原因：

1. server 现有 VLM 调用需要 frame evidence
2. `clip_id` 本身不包含图片证据
3. 复用 `InspectCandidate` 可以避免新增一次 clip evidence resolver
4. 最小改动更稳

建议改成：

```ts
type InspectMode = "verify" | "compare" | "choose" | "rank" | "describe";

interface InspectRequest {
  mode: InspectMode;
  task_summary: string;
  hypothesis_summary?: string | null;
  question?: string | null;
  criteria?: InspectCriterion[];
  candidates: InspectCandidate[];
}
```

`describe` 规则：

1. `candidates` 必须有 1 个或多个
2. 默认建议 1 个；第一版可限制为 1 个，降低复杂度
3. `question` 可选
4. 如果 `question` 为空，服务端使用默认 prompt：

```text
Describe this clip for an editing agent. Focus on visible subjects, actions, scene, timing, camera motion, mood, and uncertainty. Do not invent details.
```

### 4.2 Response

为了不拆接口，可以扩展现有 `InspectResponse`：

```ts
interface InspectDescription {
  clip_id: string;
  description: string;
  observations: string[];
  actions?: string[];
  subjects?: string[];
  scene?: string | null;
  camera?: string | null;
  editing_value?: string | null;
  uncertainty?: string | null;
}

interface InspectResponse {
  question_type: "verify" | "compare" | "choose" | "rank" | "describe";
  selected_clip_id?: string | null;
  ranking?: string[] | null;
  candidate_judgments?: CandidateJudgment[];
  descriptions?: InspectDescription[];
  uncertainty?: string | null;
}
```

兼容规则：

1. 旧 mode 继续要求 `candidate_judgments` 非空
2. `describe` 要求 `descriptions` 非空
3. `describe` 可以把 `selected_clip_id` 设置为被描述的 `clip_id`
4. `candidate_judgments` 在 `describe` 下不强制存在

## 5. Server service 最小改动

### 5.1 `_validate_semantics`

新增分支：

```python
if payload.mode == "describe":
    if candidate_count != 1:
        raise invalid_inspect_request("describe mode requires exactly one candidate.")
    validate frames as before
    return
```

说明：

第一版限制一个 candidate 是更好的 KISS 选择。多个 clip 比较已经由 `compare/choose/rank` 承担；`describe` 的定位是“看懂某个 clip”。

### 5.2 `_build_upstream_payload`

新增 describe 专用 system prompt。

旧 mode 使用当前判断 prompt。

`describe` system prompt 建议：

```text
You are the visual perception tool for a text-only video editing agent.
Return exactly one JSON object.
Describe only visible evidence from the provided clip frames.
Separate observations from inferences.
Mention uncertainty when the frames are insufficient.
Do not invent identities, events, emotions, or off-screen facts.
Use top-level fields: question_type, selected_clip_id, descriptions, uncertainty.
descriptions must contain objects with clip_id, description, observations, actions, subjects, scene, camera, editing_value, uncertainty.
```

user prompt 由：

1. `task_summary`
2. `hypothesis_summary`
3. `question` 或默认 describe prompt
4. candidate metadata
5. ordered frames

共同组成。

### 5.3 `_normalize_provider_response`

新增 describe 分支：

1. 解析 JSON
2. 补 `question_type = "describe"`
3. 校验 `descriptions` 是非空数组
4. 校验每个 `description.clip_id` 属于 request candidates
5. 如果没有 `selected_clip_id`，设置为第一个 `description.clip_id`
6. 不要求 `candidate_judgments`

旧 mode 保持当前逻辑。

## 6. Core context 最小改动

文件：`core/context.py`

### 6.1 Tool descriptor

把 `inspect` 从“候选判优”改成“双职责”：

```text
purpose:
深入理解已知 clip，或对少量候选进行比较、消歧与质量判断

when_to_use:
用户指定某个 clip、需要确认视觉细节、需要看懂某个候选、或多个候选需要进一步判优时

when_not_to_use:
当前没有任何可定位 clip，或只是需要从素材池寻找候选时
```

### 6.2 Planner system prompt

把：

```text
For scope expansion, retrieve first; for candidate judgment, inspect.
```

改成：

```text
Use retrieve to find candidate clips. Use inspect to understand a known clip or judge a small candidate set. If the user names a specific clip or the visual details are uncertain, inspect can be used without another retrieval step.
```

## 7. Core execution 最小改动

文件：

1. `core/agent.py`
2. `core/inspection.py`

第一阶段可以先不直接接 server VLM，只把 tool input 和状态语义打通；但这会让 `describe` 名义上存在、实际仍是本地摘要。

更推荐的最小可用实现：

1. `tool_input` 支持：

```json
{
  "mode": "describe",
  "clip_id": "clip_xxx",
  "question": "Describe the visible actions and editing value of this clip."
}
```

2. `core/agent.py` 识别 `mode`
3. `mode=describe` 时先选中目标 clip
4. 如果当前 clip 没有 frame evidence，返回明确错误或 fallback 到本地 summary
5. 如果已有 frame evidence，则调用 server `/v1/tools/inspect`

注意：

当前 `ClipModel` 是否包含可直接发送给 server 的 `frames[].image_base64` 需要单独核查。如果没有，则本轮必须补一个 evidence resolver；否则 server describe 无法真正工作。

## 8. 测试切入点

### 8.1 Server tests

文件：`server/tests/test_inspect_routes.py`

新增：

1. `test_inspect_describe_accepts_single_candidate`
2. `test_inspect_describe_rejects_multiple_candidates`
3. `test_inspect_describe_uses_default_question_when_missing`
4. `test_inspect_describe_normalizes_description_response`
5. `test_inspect_describe_rejects_unknown_description_clip_id`

### 8.2 Core tests

文件：

1. `core/tests/test_context_engineering.py`
2. 视现状新增或修改 Agent tool execution test

新增断言：

1. tool context 中 `inspect` 不再被描述为必须依赖 `retrieve`
2. planner prompt 明确 `Inspect` 可以理解已知 clip
3. `tool_input.mode=describe` 能被执行层识别

## 9. 推荐实施顺序

1. 修改 `server/app/schemas/inspect.py`
2. 修改 `server/app/services/inspect.py`
3. 补 `server/tests/test_inspect_routes.py`
4. 修改 `core/context.py`
5. 检查 `core/schemas.py` 的 tool input 是否需要显式字段
6. 修改 `core/agent.py` 与 `core/inspection.py`
7. 补 core 测试
8. 手动在 `/docs` 验证 `/v1/tools/inspect` 出现 `describe` mode

## 10. 手动调试参数

最小 `describe` 请求：

```json
{
  "mode": "describe",
  "task_summary": "Agent needs to understand this clip before deciding whether to use it.",
  "question": "Describe the visible subjects, actions, scene, camera movement, and editing value of this clip.",
  "candidates": [
    {
      "clip_id": "clip_001",
      "asset_id": "asset_001",
      "clip_duration_ms": 5000,
      "summary": "Optional existing local summary.",
      "frames": [
        {
          "frame_index": 0,
          "timestamp_ms": 0,
          "timestamp_label": "00:00",
          "image_base64": "<BASE64_JPEG_FRAME>"
        },
        {
          "frame_index": 1,
          "timestamp_ms": 2500,
          "timestamp_label": "00:02.500",
          "image_base64": "<BASE64_JPEG_FRAME>"
        }
      ]
    }
  ]
}
```

注意：

`image_base64` 只填纯 base64，不要带 `data:image/jpeg;base64,` 前缀。当前 server 会自己拼接。

## 11. 断点位置

Server 侧：

1. `server/app/api/routes/inspect.py:tools_inspect`
   - 看 request body 是否进入 `mode=describe`
2. `server/app/services/inspect.py:validate_request`
   - 看 Pydantic 校验是否通过
3. `server/app/services/inspect.py:_validate_semantics`
   - 看 describe 的候选数量和 frame evidence 校验
4. `server/app/services/inspect.py:_build_upstream_payload`
   - 看 system prompt 和 image payload 是否正确
5. `server/app/services/inspect.py:_normalize_provider_response`
   - 看 provider JSON 是否归一化为 `descriptions`

Core 侧：

1. `core/context.py:build_tool_capability_state`
   - 看 planner 是否拿到新的 inspect 描述
2. `core/context.py:build_planner_system_prompt`
   - 看 planner system prompt 是否解除 retrieve-first 限制
3. `core/agent.py` 的 `tool_call.tool_name == "inspect"` 分支
   - 看 `tool_input.mode`、`clip_id`、`question` 是否被保留
4. `core/inspection.py`
   - 看本地 fallback 或 server inspect 调用输入是否正确

## 12. 关键风险

最大风险不是 Schema，而是 `core` 是否能拿到真实 frame evidence。

如果 `core` 当前只有 `clip.visual_desc`、`thumbnail_ref`，没有关键帧 base64，则 server 的 `describe` mode 虽然可用，但 Agent 无法自动构造请求。此时需要在 core 增加一个很薄的 evidence resolver：

1. 从 `thumbnail_ref` 或 clip frame refs 读取图片
2. 转成 base64
3. 组装 `InspectCandidate.frames`
4. 调 server `/v1/tools/inspect`

这个 resolver 应该保持局部，不要把素材读取逻辑散进 planner。

