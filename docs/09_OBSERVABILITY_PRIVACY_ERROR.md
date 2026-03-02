# 09. Observability / Privacy / Error（可观测性 / 隐私 / 错误语义）

## 1. Logging（日志）

关键日志字段：

1. `request_id`
2. `user_id`
3. `project_id`
4. `session_id`
5. `endpoint`
6. `latency_ms`
7. `error_code`

要求：

1. `core` 与 `server` 均输出结构化日志（`JSON Log`）。
2. 客户端错误需携带关联 `request_id`，便于跨服务排障。

## 2. Metrics（指标）

MVP 必备指标：

1. `ingest_latency_ms`
2. `vector_upsert_latency_ms`
3. `retrieval_latency_ms`
4. `plan_latency_ms`
5. `refine_latency_ms`
6. `render_start_latency_ms`
7. `export_success_rate`

## 3. Trace（链路追踪）

1. `client` 发起请求时生成 `request_id`。
2. `core/server` 透传并记录 `request_id`。
3. 多轮会话通过 `session_id` 关联。

## 4. Privacy（隐私）

1. 不上传原始视频流到云端。
2. 云端存储仅包含：
   1. 向量
   2. `user_id`
   3. `file_path`
   4. `time_range`
3. 所有检索必须附带 `user_id` 过滤。
4. 不在日志记录完整 `Base64` 内容。

## 5. Error Semantics（错误语义）

统一错误结构：

```json
{
  "error": {
    "code": "CORE_RENDER_FAILED",
    "message": "Render preview failed.",
    "details": {
      "request_id": "req_001",
      "retryable": true
    }
  }
}
```

错误分级：

1. `4xx`：输入错误、鉴权失败、资源不存在。
2. `5xx`：服务失败、超时、依赖故障。

规则：

1. 禁止吞错，必须返回可枚举 `code`。
2. `message` 稳定，对外可读。
3. `details` 可选，禁止泄露密钥与内部路径。
