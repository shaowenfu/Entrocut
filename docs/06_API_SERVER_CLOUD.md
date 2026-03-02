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

## 3. `POST /api/v1/agent/plan`

用途：根据用户自然语言生成第一版 `EntroVideoProject`。

请求：

```json
{
  "project_id": "proj_001",
  "session_id": "sess_001",
  "user_prompt": "帮我剪辑一个30秒慢节奏京都视频",
  "context": {
    "asset_ids": ["asset_001"],
    "target_duration_ms": 30000
  }
}
```

响应：

```json
{
  "project": {
    "contract_version": "1.0.0",
    "project_id": "proj_001"
  },
  "reasoning_summary": "优先召回寺庙与街景空镜，控制镜头运动幅度。",
  "retrieval": {
    "query_keywords": ["Kyoto temple", "quiet street", "slow pace"],
    "top_k": 20
  }
}
```

## 4. `POST /api/v1/agent/refine`

用途：基于用户反馈微调当前剪辑方案。

请求：

```json
{
  "project_id": "proj_001",
  "session_id": "sess_001",
  "selected_item_id": "item_003",
  "user_prompt": "这个镜头有人，换个没人且构图更好的",
  "current_project": {
    "contract_version": "1.0.0",
    "project_id": "proj_001"
  }
}
```

响应：

```json
{
  "patch": {
    "replace_item_id": "item_003",
    "new_clip_id": "clip_287"
  },
  "reasoning": "新镜头人像干扰更少，水平构图更稳定。"
}
```

## 5. `POST /api/v1/chat`

用途：兼容客户端统一消息入口（可路由到 `plan/refine`）。

请求：

```json
{
  "project_id": "proj_001",
  "session_id": "sess_001",
  "message": "换个音乐"
}
```

响应：

```json
{
  "intent": "REFINE_AUDIO",
  "next_action": "UPDATE_PROJECT_CONTRACT"
}
```

## 6. 数据隔离规则

1. 每次向量检索必须追加 `filter: user_id = current_user`。
2. `project_id` 不作为唯一隔离边界，必须和 `user_id` 联合校验。
3. 禁止跨用户检索。

## 7. 错误码（Server）

1. `SERVER_AUTH_UNAUTHORIZED`
2. `SERVER_VECTOR_TIMEOUT`
3. `SERVER_VECTOR_UPSERT_FAILED`
4. `SERVER_LLM_TIMEOUT`
5. `SERVER_CONTRACT_INVALID`
