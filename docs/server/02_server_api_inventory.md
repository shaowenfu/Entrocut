# Server API Inventory（服务端接口清单）

本文档基于 [01_server_module_design.md](./01_server_module_design.md) 收口 `Server` 的完整接口边界。目标是把 `Server` 明确为一个以 `Auth（鉴权）`、`AI Model Proxy & Gateway（模型中转站）`、`Quota / Rate Limit（额度与限流）`、`Vector / RAG（向量与检索）` 为核心的云端服务。

## 1. 设计原则

1. `Server` 只负责身份验证、安全中转、额度账本、资源调度，不承载本地 `Core` 的工程状态。
2. `Core -> Server` 的开放式推理统一走 `POST /v1/chat/completions`，保持 `OpenAI-compatible（OpenAI 兼容）`；专用工具能力走独立 `REST endpoints`。
3. `Client` 是唯一的 `refresh owner（刷新责任方）`，`Core` 只消费最新 `access token`。
4. `Server` 内部统一使用 `_id`，对外响应才映射为 `id`。
5. `login_session` 是 `one-shot consume（一 次性消费）`，`deep link` 中不传 token。
6. `streaming（流式）` 优先；`vectorize（向量化）` 必须保证“向量化 + 入库”的原子语义。

## 2. 接口清单总表

| 模块 | 路径 | 方法 | 鉴权 | 核心输入 | 核心输出 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| Runtime | `/health` | `GET` | 否 | - | 服务状态、依赖状态 | current |
| Runtime | `/api/v1/runtime/capabilities` | `GET` | 否 | - | 当前开放能力清单 | current |
| Auth | `/api/v1/auth/login-sessions` | `POST` | 否 | `provider`, `client_redirect_uri` | `login_session_id`, `authorize_url`, `expires_in` | current |
| Auth | `/api/v1/auth/oauth/{provider}/start` | `GET` | 否 | `login_session_id` | 302 跳转到 OAuth provider | current |
| Auth | `/api/v1/auth/oauth/{provider}/callback` | `GET` | 否 | `code`, `state` | 302 跳回 `Client` 或 `deep link` | current |
| Auth | `/api/v1/auth/login-sessions/{login_session_id}` | `GET` | 否 | `login_session_id` | 一次性领取登录结果 | current |
| Auth | `/api/v1/auth/dev/fallback` | `GET` | 否 | `login_session_id`, `status` | 开发期网页登录回流页 | current |
| Auth Test | `/api/v1/test/bootstrap/login-session` | `POST` | `X-Bootstrap-Secret` | `login_session_id`, `provider` | 仅 `staging` 用于注入测试登录态 | current |
| Auth | `/api/v1/auth/refresh` | `POST` | 否 | `refresh_token` | 新 `access_token` + 新 `refresh_token` | current |
| Auth | `/api/v1/auth/logout` | `POST` | 是 | `Authorization: Bearer <access_token>` | 登出成功 | current |
| User | `/api/v1/me` | `GET` | 是 | `Authorization` | 当前用户资料、额度信息 | current |
| User | `/user/profile` | `GET` | 是 | `Authorization` | `membership`, `remaining_quota`, `quota_status` | current |
| User | `/user/usage` | `GET` | 是 | `Authorization` | Token 消耗、订阅状态、剩余额度 | current |
| AI Proxy | `/v1/chat/completions` | `POST` | 是 | `messages`, `model`, `stream` | `OpenAI-compatible` 响应或 `SSE` | current |
| Vector | `/v1/assets/vectorize` | `POST` | 是 | `clip contact sheets[]`, `metadata` | 向量化并入库结果 | current |
| Retrieval | `/v1/assets/retrieval` | `POST` | 是 | `query_text`, `topk`, `filter` | 命中素材 ID、分数、元数据 | current |
| Tool | `/v1/tools/inspect` | `POST` | 是 | `mode`, `question`, `candidates[].frames[]` | 结构化候选判定结果 | planned |

## 3. 模块说明

### 3.1 Auth（鉴权）

#### `POST /api/v1/auth/login-sessions`
- 用途：创建一次性 `login_session`，作为 `OAuth` 与 `Client`/`Desktop` 的桥接句柄。
- 请求：
```json
{
  "provider": "google",
  "client_redirect_uri": "entrocut://auth/callback"
}
```
- 响应：
```json
{
  "login_session_id": "login_xxx",
  "authorize_url": "https://server/api/v1/auth/oauth/google/start?...",
  "expires_in": 600
}
```

#### `GET /api/v1/auth/oauth/{provider}/start`
- 用途：跳转到 `OAuth provider（OAuth 提供方）`。
- 备注：当前首个 `provider` 为 `google`。

#### `GET /api/v1/auth/oauth/{provider}/callback`
- 用途：消费 `code/state`，落用户、签发 `JWT access/refresh token`，再回跳 `Client`。
- 约束：
1. 不在回跳 URL 中直接暴露 token。
2. 回跳只携带 `login_session_id + status`。

#### `GET /api/v1/auth/login-sessions/{login_session_id}`
- 用途：由 `Client` 一次性领取登录结果。
- 状态机：
1. `pending`
2. `authenticated`
3. `consumed`
4. `failed`
- 约束：`login_session` 只能被成功领取一次；重复领取必须返回 `status=consumed` 且 `result=null`。

#### `POST /api/v1/auth/refresh`
- 用途：由 `Client` 执行 `refresh rotation（刷新轮换）`。
- 约束：
1. 只允许 `Client` 刷新。
2. 刷新后旧 `refresh_token` 立即失效。

#### `POST /api/v1/auth/logout`
- 用途：撤销当前会话。
- 影响：
1. 当前 `session` 失效。
2. 对应 `refresh_token` 失效。
3. `Client` 需要同步清空 `Core` 本地会话。

### 3.2 User & Quota（用户与额度）

#### `GET /api/v1/me`
- 用途：当前已实现的用户信息入口。
- 最小返回字段：
```json
{
  "user": {
    "id": "user_xxx",
    "email": "name@example.com",
    "name": "Example User",
    "avatar_url": "https://...",
    "remaining_quota": 4926,
    "quota_status": "healthy"
  }
}
```

#### `GET /user/profile`
- 用途：面向 `Client/Core` 的稳定用户画像接口。
- 推荐字段：
1. `id`
2. `email`
3. `name`
4. `avatar_url`
5. `membership_plan`
6. `remaining_quota`
7. `quota_status`
8. `subscription_status`

#### `GET /user/usage`
- 用途：返回消费账本摘要，而不是完整内部账本。
- 推荐字段：
1. `remaining_quota`
2. `consumed_tokens_today`
3. `consumed_tokens_this_month`
4. `rate_limit_status`
5. `subscription_status`

### 3.3 AI Model Proxy & Gateway（模型中转站）

#### `POST /v1/chat/completions`
- 用途：统一承接 `Core` 的模型推理请求。
- 边界：只承接 `planner` 与开放式对话，不承接专用 `inspect` 工具调用。
- 请求：保持 `OpenAI-compatible`。
```json
{
  "model": "entro-reasoning-v1",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." }
  ],
  "stream": true
}
```

- 服务端逻辑：
1. 校验 `JWT`
2. 校验 `quota`
3. 执行 `rate limit`
4. 将虚拟模型名路由到真实 `provider model`
5. 注入 `Master API Key`
6. 转发到上游 `LLM provider`
7. 回写 `usage ledger`
8. 在结束块附带 `entro_metadata`

- 非流式响应：
1. 保持 `OpenAI-compatible JSON`
2. 附带 `usage`
3. 附带 `entro_metadata.remaining_quota`

- 流式响应：
1. 使用 `SSE`
2. 中间块透传 `choices[0].delta`
3. 最终块附带 `usage + entro_metadata`
4. 最后一块输出 `data: [DONE]`

- 推荐 `entro_metadata`：
```json
{
  "remaining_quota": 4800,
  "quota_status": "healthy",
  "user_id": "user_xxx"
}
```

- 典型错误：
1. `401 AUTH_TOKEN_MISSING`
2. `401 AUTH_TOKEN_INVALID`
3. `402 QUOTA_EXCEEDED`
4. `429 RATE_LIMITED`
5. `502 MODEL_PROVIDER_UNAVAILABLE`
6. `501 CHAT_STREAM_NOT_SUPPORTED`

### 3.4 Vector & RAG（向量与检索）

#### `POST /v1/assets/vectorize`
- 用途：执行“向量化 + 入库”的原子操作。
- 请求：
```json
{
  "docs": [
    {
      "id": "clip_001",
      "content": {
        "image_base64": "..."
      },
      "fields": {
        "clip_id": "clip_001",
        "asset_id": "asset_001",
        "project_id": "proj_001",
        "source_start_ms": 1200,
        "source_end_ms": 4800
      }
    }
  ]
}
```

- 服务端逻辑：
1. 校验 `JWT`
2. 调用 `Embedding provider`
3. 直接写入 `Vector DB`
4. 成功后返回写入结果

- 原子语义：
1. 若 `embedding` 成功但 `Vector DB insert` 失败，整个请求返回明确错误
2. `Core` 只接收“成功写入”或“明确失败”，不接收裸向量
3. 当前阶段主输入是 `clip contact sheet image_base64`，不上传原始视频

#### `POST /v1/assets/retrieval`
- 用途：执行语义检索。
- 请求：
```json
{
  "query_text": "滑雪跃起的动作",
  "top_k": 8,
  "filters": {
    "project_id": "proj_001"
  }
}
```

- 边界：
1. 当前阶段只做纯向量主召回
2. 不做 `inspect` 级精判
3. 不支持 `query_image / query_video`

- 响应：
```json
{
  "matches": [
    {
      "asset_id": "asset_001",
      "score": 0.92,
      "metadata": {
        "project_id": "proj_001"
      }
    }
  ]
}
```

#### `POST /v1/tools/inspect`
- 用途：对小规模候选 `clip` 做图像级结构化判定。
- 当前形态：
1. 输入候选的多关键帧序列
2. 每张关键帧都带时间位置
3. 同时附带片段总时长
4. 服务端调用 `Gemini` 等图像多模态模型
5. 返回 `verify / compare / choose / rank` 结果
- 非目标：
1. 不做整段视频理解
2. 不做开放式聊天
3. 不直接生成 `EditDraftPatch`

## 4. 推荐错误语义

| HTTP | code | 语义 |
| --- | --- | --- |
| `401` | `AUTH_TOKEN_MISSING` | 缺少 `Bearer token` |
| `401` | `AUTH_TOKEN_INVALID` | token 非法、过期、撤销 |
| `402` | `QUOTA_EXCEEDED` | 用户额度不足 |
| `403` | `USER_SUSPENDED` | 用户被禁用 |
| `404` | `LOGIN_SESSION_NOT_FOUND` | 登录会话不存在 |
| `409` | `LOGIN_SESSION_CONSUMED` | 登录会话已被消费 |
| `422` | `INVALID_CHAT_MESSAGES` | `messages` 非法 |
| `422` | `INVALID_VECTORIZE_REQUEST` | 向量化参数非法 |
| `429` | `RATE_LIMITED` | 触发 `RPM/TPM` 限流 |
| `502` | `PROVIDER_TRANSPORT_ERROR` | 上游模型连接或传输失败 |
| `502` | `MODEL_PROVIDER_INVALID_RESPONSE` | 上游模型返回非法响应 |
| `502` | `MODEL_PROVIDER_UNAVAILABLE` | 上游模型失败 |
| `504` | `PROVIDER_TIMEOUT` | 上游模型超时 |
| `502` | `VECTOR_PROVIDER_UNAVAILABLE` | 向量服务失败 |
| `503` | `DEPENDENCY_UNAVAILABLE` | `MongoDB/Redis/Vector DB` 不可用 |

## 5. 当前落地范围与上线前收尾

### current（已全部落地）
1. `Auth phase 1`
2. `JWT access/refresh token`
3. `/api/v1/me`
4. `/user/profile`
5. `/user/usage`
6. `/v1/chat/completions`
7. `chat proxy SSE streaming（聊天代理流式返回）`
8. `quota / rate limit`
9. `Google OAuth`
10. `MongoDB Atlas + Redis`
11. `/v1/assets/vectorize`
12. `/v1/assets/retrieval`
13. `DashScope + DashVector` 真实联调

### hardening（上线前收尾）
1. `observability（可观测性）`：统一 `structured logging（结构化日志）`、`metrics（指标）`、`alerts（告警）`
2. `dependency resilience（依赖韧性）`：收口 `MongoDB / Redis / provider / DashScope / DashVector` 的错误分级与降级策略
3. `security hardening（安全加固）`：`.env` 密钥治理、生产 `CORS` 白名单、`dev fallback` 生产禁用、限额与限流阈值校准
4. `deployment readiness（部署就绪）`：补启动检查、健康检查分层、运行手册与告警手册
