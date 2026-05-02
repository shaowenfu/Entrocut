# EntroCut Server

`server/` 是 EntroCut 的云端能力网关。它不负责本地剪辑、不直接管理桌面工作区文件，而是为 `core/` 和 `client/` 提供稳定的云端 `HTTP API（超文本传输接口）`：认证、用户状态、`OpenAI-compatible chat proxy（兼容 OpenAI 的聊天代理）`、素材向量化、检索、视觉精判，以及运行态健康检查。

当前实现可以概括为：

```text
Client / Core
    |
    |  HTTP + Bearer token（持有者令牌）
    v
Server FastAPI
    |
    +-- OAuth / JWT / Refresh Token（登录与会话）
    +-- Chat Proxy（模型调用代理）
    +-- Credits + Rate Limit（额度与限流）
    +-- DashScope Embedding + DashVector（多模态向量化与检索）
    +-- Gemini Inspect（视觉候选精判）
    +-- Metrics / Health / Runtime Capabilities（观测与能力声明）
```

## 核心目录导航

```text
server/
├── README.md                         # 当前文档：server 真实代码现状与阅读入口
├── requirements.txt                  # Python 依赖清单；当前无 pyproject.toml
├── Dockerfile                        # 容器镜像构建入口，默认暴露 8001
├── main.py                           # 兼容入口：导出 FastAPI app
├── .env.example                      # 环境变量样例；真实 .env 不应提交敏感值
├── app/
│   ├── main.py                       # 应用稳定导出层：app 与核心 service 单例
│   ├── bootstrap/                    # FastAPI 装配层
│   │   ├── app.py                    # 创建 FastAPI app、注册 CORS、middleware、router
│   │   ├── dependencies.py           # settings、store、service、metrics 等运行态单例
│   │   ├── lifespan.py               # 启动期校验依赖、索引、健康状态
│   │   ├── middleware.py             # request_id、结构化日志、HTTP metrics
│   │   └── exception_handlers.py     # 统一错误 envelope 与依赖错误处理
│   ├── api/
│   │   ├── router.py                 # 路由聚合入口
│   │   └── routes/
│   │       ├── health.py             # /health、/livez、/readyz、/metrics
│   │       ├── runtime.py            # / 与 /api/v1/runtime/capabilities
│   │       ├── auth.py               # OAuth login session、callback、refresh、logout、me
│   │       ├── users.py              # /user/profile 与 /user/usage
│   │       ├── chat.py               # /v1/chat/completions
│   │       ├── assets.py             # /v1/assets/vectorize 与 /v1/assets/retrieval
│   │       └── inspect.py            # /v1/tools/inspect
│   ├── core/
│   │   ├── config.py                 # Settings（配置模型）与 RATE_CARDS（计费卡）
│   │   ├── errors.py                 # ServerApiError 与可枚举错误工厂
│   │   ├── observability.py          # JSON log、audit log、Prometheus-style metrics
│   │   └── runtime_guard.py          # staging/production 强配置校验
│   ├── schemas/                      # Pydantic schema（请求 / 响应契约）
│   │   ├── auth.py                   # 登录会话、refresh、logout schema
│   │   ├── user.py                   # 用户资料与用量快照 schema
│   │   ├── runtime.py                # runtime capabilities schema
│   │   ├── assets.py                 # vectorize / retrieval schema
│   │   ├── inspect.py                # inspect 请求与响应 schema
│   │   └── common.py                 # 通用 schema 占位
│   ├── repositories/                 # 数据访问层
│   │   ├── auth_store.py             # 组合 MongoRepository 与 LoginSessionStore
│   │   ├── mongo_repository.py       # MongoDB 持久化；本地可回退进程内存
│   │   └── login_session_repository.py # Redis 登录会话；本地可回退进程内存
│   ├── services/
│   │   ├── auth/                     # OAuth、JWT、用户 upsert、token hash 工具
│   │   ├── gateway/                  # 模型网关、provider routing、streaming、billing
│   │   ├── quota.py                  # Redis / memory rate limit 与 quota 辅助
│   │   ├── vector.py                 # DashScope embedding + DashVector 写入 / 检索
│   │   └── inspect.py                # Gemini inspect 请求校验、调用与响应归一化
│   └── shared/
│       └── time.py                   # UTC 时间格式化工具
└── tests/
    ├── test_chat_proxy.py            # chat proxy、credits、streaming、rate limit
    ├── test_vector_routes.py         # vectorize 路由与错误语义
    ├── test_assets_retrieval.py      # retrieval 路由与错误语义
    ├── test_inspect_routes.py        # inspect 路由、证据校验、provider 响应归一化
    ├── test_user_routes.py           # 用户资料与用量接口
    ├── test_runtime_hardening.py     # production/staging 配置硬化与 metrics
    ├── test_staging_bootstrap.py     # staging 测试登录 bootstrap
    └── test_vector_service.py        # vector service 语义校验
```

补充说明：

- `server/.env` 是本地配置文件，不应作为代码契约依赖；公开样例看 `server/.env.example`。
- `docs/server/` 保存更细的设计文档和接口文档，但本 README 以当前代码事实为准。
- 当前 `server/` 下没有 `scripts/` 目录；旧文档中提到的开发脚本不是现有代码的一部分。

## 当前职责边界

`server` 的边界是云端网关，不是剪辑引擎：

1. 接收 `core` 或前端传来的 authenticated request（已认证请求）。
2. 校验 `Bearer token（持有者令牌）`，映射到用户与会话。
3. 调用上游能力：`LLM provider（大语言模型供应商）`、`DashScope（多模态 embedding）`、`DashVector（向量数据库）`、`Gemini（视觉理解模型）`。
4. 维护用户、登录会话、刷新令牌、额度与账本。
5. 输出稳定的错误语义、结构化日志、审计日志和运行态能力声明。

它不读取桌面本地视频文件，不生成 `EditDraft（剪辑草稿事实源）`，也不直接执行 `ffmpeg（音视频处理工具）`。这些职责属于 `core/`。

## 已落地能力

### 认证与用户

真实路由位于 `app/api/routes/auth.py` 与 `app/api/routes/users.py`：

| API | 说明 |
| --- | --- |
| `POST /api/v1/auth/login-sessions` | 创建 OAuth 登录会话，返回 provider 授权 URL |
| `GET /api/v1/auth/oauth/{provider}/start` | 跳转到 Google / GitHub OAuth |
| `GET /api/v1/auth/oauth/{provider}/callback` | 处理 OAuth callback，签发 access / refresh token |
| `GET /api/v1/auth/login-sessions/{id}` | 一次性领取登录结果；认证后会转为 `consumed` |
| `GET /api/v1/auth/dev/fallback` | 本地开发回落页面 |
| `POST /api/v1/test/bootstrap/login-session` | staging 测试 bootstrap，需 secret |
| `POST /api/v1/auth/refresh` | 使用 refresh token 轮换新会话 |
| `POST /api/v1/auth/logout` | 注销当前 session 与 refresh token |
| `GET /api/v1/me` | 返回当前用户资料 |
| `GET /user/profile` | 返回用户资料 |
| `GET /user/usage` | 返回 credits 与用量快照 |

认证链路的事实源：

- 用户、身份、session、refresh token、quota ledger、credit ledger 默认进入 `MongoDB（文档数据库）`。
- 本地缺少 `MONGODB_URI` 且允许 fallback 时，会退回进程内存。
- `login session（登录会话）` 和 `OAuth state（OAuth 状态）` 默认进入 `Redis（内存数据结构服务）`。
- 本地缺少或不可用 `Redis` 且允许 fallback 时，会退回进程内存。

### Chat Proxy

`POST /v1/chat/completions` 位于 `app/api/routes/chat.py`，行为接近 `OpenAI Chat Completions API（OpenAI 聊天补全接口）`。

当前主链：

1. 必须带 `Authorization: Bearer <access_token>`。
2. 校验用户状态与 `credits_balance`。
3. 按用户做 request / token 级 rate limit。
4. 根据 `LLM_PROXY_MODE` 选择 provider：
   - `mock`：本地 mock 响应。
   - `google_gemini`：转发到 Gemini OpenAI-compatible endpoint。
   - `upstream`：转发到自定义 OpenAI-compatible upstream。
5. 非流式响应会结算 credits 并写入 `entro_metadata`。
6. 流式响应会透传上游 `SSE（服务器发送事件）`，并在后台结算 usage。

相关文件：

- `app/services/gateway/provider_routing.py`
- `app/services/gateway/chat_proxy.py`
- `app/services/gateway/streaming.py`
- `app/services/gateway/billing.py`

### 向量化与检索

素材向量化和检索由 `app/api/routes/assets.py` 与 `app/services/vector.py` 承载：

| API | 说明 |
| --- | --- |
| `POST /v1/assets/vectorize` | 接收 contact sheet / keyframe 的 base64 图片，调用 DashScope embedding，写入 DashVector |
| `POST /v1/assets/retrieval` | 将 `query_text` 编码为向量，在 DashVector 中检索候选素材 |

关键约束：

- 两个接口都需要 `Bearer token（持有者令牌）`。
- `vectorize` 的 `docs[]` 不能为空，`doc.id` 不能重复。
- `source_start_ms` 必须小于 `source_end_ms`。
- `image_base64` 会先做 base64 合法性校验。
- collection 不存在时，当前代码会尝试创建 DashVector collection。
- retrieval 支持 `filter`、`topk`、`output_fields` 和 `include_vector`。

### Inspect

`POST /v1/tools/inspect` 位于 `app/api/routes/inspect.py`，用于让云端视觉模型对候选片段做精判。

当前支持的 `mode（模式）`：

- `verify`：只允许 1 个候选。
- `compare`：只允许 2 个候选。
- `choose`：允许 3 到 5 个候选。
- `rank`：允许 2 到 5 个候选。

每个候选必须提供：

- `clip_id`
- `asset_id`
- 正数 `clip_duration_ms`
- 至少一帧 `frames[]`
- 每帧的 `timestamp_ms`、`timestamp_label`、`image_base64`

当前 provider 只实现了 `google_gemini`。服务会要求上游返回 JSON，然后归一化为 `InspectResponse`，包括 `selected_clip_id`、`ranking`、`candidate_judgments` 和 `uncertainty`。

### 运行态与观测

| API | 说明 |
| --- | --- |
| `GET /` | 返回 server 基本信息与关键配置是否存在 |
| `GET /health` | 返回服务状态、版本、环境、依赖健康与说明 |
| `GET /livez` | 存活探针 |
| `GET /readyz` | 就绪探针；严格环境下依赖失败会返回 503 |
| `GET /metrics` | Prometheus-style metrics；可由 `OBSERVABILITY_ENABLE_METRICS` 关闭 |
| `GET /api/v1/runtime/capabilities` | 返回当前保留 API surface 与云端能力可用性 |

日志采用 JSON 结构化输出，并通过 `request_id` 串联请求、错误和审计事件。客户端也可以传入 `X-Request-ID`。

## 错误语义

统一错误响应由 `ServerApiError` 和 `ErrorEnvelope` 生成：

```json
{
  "error": {
    "code": "AUTH_TOKEN_MISSING",
    "message": "Authorization header is required.",
    "type": "auth_error",
    "details": {
      "request_id": "req_xxx"
    },
    "request_id": "req_xxx"
  }
}
```

典型错误码：

- `AUTH_TOKEN_MISSING` / `AUTH_TOKEN_INVALID` / `AUTH_TOKEN_EXPIRED`
- `INSUFFICIENT_CREDITS`
- `RATE_LIMITED`
- `VECTOR_CONFIG_ERROR`
- `INVALID_VECTORIZE_REQUEST`
- `EMBEDDING_PROVIDER_UNAVAILABLE`
- `VECTOR_STORE_UNAVAILABLE`
- `INVALID_RETRIEVAL_REQUEST`
- `QUERY_EMBEDDING_FAILED`
- `RETRIEVAL_FAILED`
- `INVALID_INSPECT_REQUEST`
- `INSPECT_EVIDENCE_MISSING`
- `INSPECT_PROVIDER_UNAVAILABLE`
- `INSPECT_PROVIDER_INVALID_RESPONSE`
- `DEPENDENCY_UNAVAILABLE`
- `SERVER_INTERNAL_ERROR`

## 配置要点

配置模型在 `app/core/config.py`，样例在 `.env.example`。

本地开发常见配置：

```bash
APP_ENV=local
SERVER_PORT=8001
SERVER_BASE_URL=http://127.0.0.1:8001
AUTH_JWT_SECRET=entrocut-dev-secret-change-me
AUTH_DEV_FALLBACK_ENABLED=true
ALLOW_INMEMORY_MONGO_FALLBACK=true
ALLOW_INMEMORY_REDIS_FALLBACK=true
LLM_PROXY_MODE=mock
```

连接真实 provider 时需要按能力补齐：

```bash
# OAuth
AUTH_GOOGLE_CLIENT_ID=
AUTH_GOOGLE_CLIENT_SECRET=
AUTH_GITHUB_CLIENT_ID=
AUTH_GITHUB_CLIENT_SECRET=

# Chat / Inspect
LLM_PROXY_MODE=google_gemini
GOOGLE_API_KEY=

# Vectorize / Retrieval
DASHSCOPE_API_KEY=
DASHVECTOR_API_KEY=
DASHVECTOR_ENDPOINT=
```

`staging（预发布）` 或 `production（生产）` 下 `runtime_guard.py` 会强制：

- 替换默认 `AUTH_JWT_SECRET`。
- 关闭 `AUTH_DEV_FALLBACK_ENABLED`。
- 配置 `MONGODB_URI` 与 `REDIS_URL`。
- 关闭内存 fallback。
- `production` 的 CORS 不允许包含 `localhost` 或 `127.0.0.1`。

## 本地运行

遵循仓库约定，Python 命令先激活虚拟环境：

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/api/v1/runtime/capabilities
```

容器入口见 `Dockerfile`，默认命令：

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips=*
```

## 测试

当前测试覆盖了认证保护、chat proxy、向量化、检索、inspect、用户接口和运行态硬化：

```bash
cd server
source venv/bin/activate
pytest
```

建议优先关注：

1. `tests/test_chat_proxy.py`
2. `tests/test_vector_routes.py`
3. `tests/test_assets_retrieval.py`
4. `tests/test_inspect_routes.py`
5. `tests/test_runtime_hardening.py`

## 推荐阅读顺序

如果你想从系统边界入手：

1. `app/core/config.py`：先看配置面，理解当前 server 的可变参数。
2. `app/core/errors.py`：再看错误契约，明确客户端可分支处理的失败类型。
3. `app/bootstrap/dependencies.py`：看运行态单例如何装配。
4. `app/api/router.py` 和 `app/api/routes/`：看真实 API surface。
5. `app/services/auth/`：看 OAuth、JWT、refresh token 与用户 upsert。
6. `app/services/gateway/`：看 chat proxy、streaming、billing。
7. `app/services/vector.py` 与 `app/services/inspect.py`：看云端素材理解能力。
8. `app/repositories/`：最后看 MongoDB / Redis fallback 细节。

如果只想快速理解 `Core -> Server` 主链，读这四个文件即可：

1. `app/api/routes/chat.py`
2. `app/api/routes/assets.py`
3. `app/api/routes/inspect.py`
4. `app/bootstrap/dependencies.py`

## 当前 Non-goals

当前 `server` 明确不做：

1. 不做本地视频文件扫描、切片、缩略图、preview 或 export。
2. 不存储 `EditDraft（剪辑草稿事实源）`，也不决定最终剪辑结构。
3. 不实现完整 `admin panel（管理后台）`。
4. 不实现团队级 `RBAC（基于角色的访问控制）`。
5. 不承诺完整产品化 `credits settlement（额度结算）`；当前是可回归的 MVP 账本链路。
6. 不承诺完整 `BYOK provider compatibility（用户自带密钥供应商兼容矩阵）`。
7. 不在生产环境允许内存 fallback、默认 JWT secret 或 dev fallback 登录页。
8. 不把 `mock` chat proxy 视为真实模型质量能力。

## 后续方向

1. 收紧 `LLM_PROXY_MODE` 的可枚举配置，避免非法值只在运行时暴露。
2. 把 `credits_balance`、`quota_*`、`RateLimitService` 的职责进一步统一，减少两套额度概念并存。
3. 为 `VectorService` 增加更多 provider-level contract test（供应商契约测试）。
4. 为 streaming billing 增加失败路径和中断路径回归。
5. 明确 `Inspect` 的模型输出 schema 版本，便于 `core` 做稳定调用。
6. 将 `docs/server/` 中仍停留在设计态的内容标注为 proposed / implemented，避免文档混淆。
