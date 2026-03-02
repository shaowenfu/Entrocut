# 06. Server API（云端编排接口）

Base URL: `https://api.entrocut.com`

## 1. `GET /health`

用途：基础探活。

## 2. `POST /api/v1/index/upsert-clips`

用途：对 `core` 提供的关键帧拼图执行向量化并写入 `DashVector`。

请求：

```json
{
  "project_id": "proj_001",
  "user_id": "user_001",
  "clips": [
    {
      "clip_id": "clip_001",
      "file_path": "D:/Videos/travel_kyoto.mp4",
      "time_range": {
        "start_ms": 12000,
        "end_ms": 16800
      },
      "frame_pack_base64": "<omitted>"
    }
  ]
}
```

响应：

```json
{
  "indexed": 1,
  "failed": 0
}
```

规则：

1. 向量写入必须携带 `user_id`。
2. 不存储视频内容，仅存向量与最小元数据。

## 3. `POST /api/v1/chat`

用途：`Agent` 唯一对外交互入口。所有 `Context Engineering（上下文工程）`、`Intent Classification（意图判断）`、`Logic Routing（逻辑路由）` 在接口内部完成。

### 3.1 请求

```json
{
  "project_id": "proj_001",
  "session_id": "sess_001",
  "user_id": "user_001",
  "message": "这个镜头有人，换个没人且构图更好的",
  "context": {
    "asset_ids": ["asset_001"],
    "selected_item_id": "item_003",
    "target_duration_ms": 30000
  },
  "current_project": {
    "contract_version": "1.0.0",
    "project_id": "proj_001"
  }
}
```

字段说明：

1. `message` 为自然语言主输入。
2. `context` 为轻量级界面上下文，可选。
3. `current_project` 为当前契约快照，可选；首次生成可不传。

### 3.2 响应

统一返回 `AgentDecision`，根据 `decision_type` 决定客户端后续动作。

```json
{
  "decision_type": "UPDATE_PROJECT_CONTRACT",
  "project": {
    "contract_version": "1.0.0",
    "project_id": "proj_001"
  },
  "patch": null,
  "reasoning_summary": "替换第3镜头为无人空镜，构图更稳定。",
  "ops": [
    {
      "op": "replace_timeline_item",
      "target_item_id": "item_003",
      "new_clip_id": "clip_287"
    }
  ],
  "meta": {
    "request_id": "req_001",
    "latency_ms": 4200
  }
}
```

说明：

1. `decision_type` 枚举：
   1. `UPDATE_PROJECT_CONTRACT`：返回完整 `project`。
   2. `APPLY_PATCH_ONLY`：返回 `patch/ops` 增量变更。
   3. `ASK_USER_CLARIFICATION`：需要用户补充信息。
2. `project` 与 `patch` 至少一个非空。
3. `reasoning_summary` 必填，用于前端展示 AI 决策依据。

### 3.3 内部逻辑（非 API 拆分）

`POST /api/v1/chat` 内部可执行以下流程，但不对外暴露为独立接口：

1. 意图识别（首次生成 / 微调 / 音频调整 / 澄清提问）。
2. 查询改写与向量检索。
3. 二次视觉理解（按需触发）。
4. 契约生成或补丁生成。

## 4. 数据隔离规则

1. 每次向量检索必须追加 `filter: user_id = current_user`。
2. `project_id` 不作为唯一隔离边界，必须和 `user_id` 联合校验。
3. 禁止跨用户检索。

## 5. 错误码（Server）

1. `SERVER_AUTH_UNAUTHORIZED`
2. `SERVER_VECTOR_TIMEOUT`
3. `SERVER_VECTOR_UPSERT_FAILED`
4. `SERVER_LLM_TIMEOUT`
5. `SERVER_CONTRACT_INVALID`
6. `SERVER_CHAT_CONTEXT_INVALID`
