# Server 上线前收尾方案

本文档面向 [01_server_module_design.md](./01_server_module_design.md) 的最终收尾阶段。目标不是继续扩接口，而是把现有 `server` 从“功能已跑通”推进到“适合云端联调、具备上线前置条件”的状态。

## 1. 当前现状

结合当前代码实现，`server` 主链已经具备：

1. `Auth（鉴权）`：`Google OAuth`、`JWT access/refresh token`、`login_session one-shot consume（一次性消费）`、`/api/v1/me`、`/user/profile`、`/user/usage`
2. `AI Model Proxy & Gateway（模型中转站）`：`/v1/chat/completions` 非流式 + `SSE streaming（流式）`、真实 `provider` 代理、`quota / rate limit` 回写
3. `Vector & Retrieval（向量与召回）`：`/v1/assets/vectorize`、`/v1/assets/retrieval`、真实 `DashScope + DashVector` 闭环
4. `Inspect Gateway（图像级候选判定）`：`/v1/tools/inspect`，当前以 `Gemini` 等图像多模态模型为主
5. `Stateful dependency（有状态依赖）`：`MongoDB Atlas`、`Redis`、`Gemini`、`DashScope`、`DashVector`

结论：功能面已经收口，当前缺口主要集中在 `operability（可运维性）`、`resilience（韧性）`、`security（安全）`，而不是业务功能。

## 2. 代码现状梳理

### 2.1 已有基础

1. [server/app/main.py](/home/sherwen/MyProjects/Entrocut_server/server/app/main.py)
   - 已有 `request_id middleware`
   - 已有统一异常处理注册
   - 已有 `/health` 与 `/api/v1/runtime/capabilities`
   - 已有 `CORS`
2. [server/app/errors.py](/home/sherwen/MyProjects/Entrocut_server/server/app/errors.py)
   - 已有稳定错误包络 `ErrorEnvelope`
   - 已有 `ServerApiError`
   - 已对外隐藏 `500` 内部异常原文
3. [server/app/quota_service.py](/home/sherwen/MyProjects/Entrocut_server/server/app/quota_service.py)
   - 已有 `QuotaService`
   - 已有 `RateLimitService`
   - 已有 `Redis unavailable -> memory fallback（Redis 不可用降级到内存）`
4. [server/app/auth_store.py](/home/sherwen/MyProjects/Entrocut_server/server/app/auth_store.py)
   - 已有 `MongoRepository`
   - 已有 `Mongo unavailable -> in-memory fallback（Mongo 不可用降级到内存）`
5. [server/app/vector_service.py](/home/sherwen/MyProjects/Entrocut_server/server/app/vector_service.py)
   - 已有外部依赖调用
   - 已有少量 `logger.exception`

### 2.2 明确缺口

1. 没有统一 `structured logging（结构化日志）`
   - 当前只有零散异常日志，且大多数路径没有日志
   - 请求进入、依赖调用、鉴权失败、限流命中、配额扣减都缺标准字段
2. 没有统一 `metrics（指标）`
   - 当前无 `/metrics`
   - 无 `request count / latency / error ratio / provider latency / quota events`
3. 没有 `alerts（告警）` 方案
   - 线上联调时一旦 `provider`、`MongoDB`、`Redis` 波动，无法第一时间定位
4. 错误分级还不够系统
   - 目前 `MongoDB`、`Redis`、`provider`、`DashScope`、`DashVector` 虽然会抛错，但没有统一映射矩阵
   - 同一类依赖错误在不同模块中的 `status_code / code / details` 还不完全对齐
5. 降级策略未正式收口
   - `MongoDB/Redis` 的 `fallback` 更适合开发，不适合生产默认启用
   - 缺少“生产环境允许什么降级、不允许什么降级”的明确边界
6. 安全收尾未完成
   - [server/app/config.py](/home/sherwen/MyProjects/Entrocut_server/server/app/config.py) 仍保留开发默认 `AUTH_JWT_SECRET`
   - [server/.env.example](/home/sherwen/MyProjects/Entrocut_server/server/.env.example) 没有区分 `required / optional / dev-only`
   - `auth_dev_fallback_enabled` 默认仍是 `true`
   - `CORS_ALLOW_ORIGINS` 仍是本地开发白名单
7. 启动与健康检查语义偏轻
   - 当前 `/health` 更偏展示，不足以作为生产依赖健康判断
   - 缺少 `readiness（就绪检查）` 与 `liveness（存活检查）`

## 3. 收尾目标

本轮收尾只做四件事：

1. 建立统一 `observability`
2. 收口依赖错误分级与降级策略
3. 收口生产安全配置
4. 明确部署前验收标准

非目标：

1. 不再新增新的业务接口
2. 不重写现有 `auth / chat / vector` 主链
3. 不引入复杂服务网格或消息队列

## 4. Workstream A：Observability

### 4.1 Structured Logging（结构化日志）

目标：所有关键路径日志统一为 `JSON log（JSON 日志）`，并携带可检索字段。

建议新增：

1. `server/app/observability.py`
   - `configure_logging(settings)`
   - `bind_request_context(request_id, user_id, route, method)`
   - `log_dependency_event(...)`
2. `server/app/logging_middleware.py`
   - 记录 `request_started`
   - 记录 `request_completed`
   - 记录 `latency_ms`

日志字段最小集合：

1. `timestamp`
2. `level`
3. `service=server`
4. `env`
5. `request_id`
6. `route`
7. `method`
8. `status_code`
9. `latency_ms`
10. `user_id` 或 `anonymous`
11. `session_id`
12. `error_code`
13. `dependency`
14. `provider`
15. `model`

必须打点的事件：

1. 鉴权失败：`AUTH_TOKEN_MISSING / INVALID / EXPIRED`
2. `login_session` 创建、领取、重复消费
3. `refresh` 成功、旧 `refresh token` 被拒绝
4. `logout`
5. `chat proxy` 请求开始、上游返回、流式结束
6. `quota exceeded`
7. `rate limited`
8. `vectorize` 调用 `DashScope`
9. `retrieval` 调用 `DashVector`
10. `inspect` 调用 `Gemini`
11. 依赖连接失败：`MongoDB / Redis / provider / DashScope / DashVector / Gemini`

落地要求：

1. 日志中禁止输出 `access token`、`refresh token`、完整 `Authorization`、API key、完整上游响应体
2. `details.upstream_body` 只保留截断摘要
3. `logger.exception` 只用于服务端内部日志，不直接映射给外部用户

### 4.2 Metrics（指标）

目标：让云端联调时能快速看清“哪里慢、哪里坏、哪里在烧额度”。

建议接入 `Prometheus（指标采集）`，新增：

1. `GET /metrics`
2. `Counter（计数器）`
3. `Histogram（延迟分布）`
4. `Gauge（瞬时值）`

核心指标：

1. `server_http_requests_total{route,method,status_code}`
2. `server_http_request_duration_ms{route,method,status_code}`
3. `server_auth_failures_total{code}`
4. `server_chat_requests_total{stream,model,provider,status}`
5. `server_chat_provider_latency_ms{provider,provider_model}`
6. `server_chat_provider_errors_total{provider,code}`
7. `server_quota_consumed_tokens_total{model,provider_model}`
8. `server_quota_exhausted_total`
9. `server_rate_limited_total{limit_type}`
10. `server_vectorize_requests_total{status}`
11. `server_vectorize_embedding_latency_ms`
12. `server_vector_db_latency_ms{operation}`
13. `server_inspect_requests_total{status,mode}`
14. `server_inspect_provider_latency_ms{provider,mode}`
15. `server_dependency_health{dependency}`

实现方式：

1. `middleware` 记录 HTTP 通用指标
2. `chat/vector` 服务层记录依赖级指标
3. `/health` 不输出指标，避免语义混杂
4. `/metrics` 仅在生产或预发环境开放给内网或受保护入口

### 4.3 Alerts（告警）

目标：先做最小可用，不追求复杂。

首批告警规则：

1. `5xx ratio` 5 分钟内超过 3%
2. `401/402/429` 突增
3. `MongoDB ping failed`
4. `Redis ping failed`
5. `provider 502/429` 突增
6. `DashScope/DashVector` 连续失败
7. `p95 latency` 超过阈值
8. `quota consumed tokens` 异常突增

输出形式：

1. 预发期先接 `Feishu / Slack webhook（告警 Webhook）`
2. 正式环境再对接统一监控平台

## 5. Workstream B：错误分级与降级策略

### 5.1 错误分级原则

把错误分成四层：

1. `client_error（客户端错误）`
   - 请求参数非法
   - token 缺失或非法
   - `login_session` 无效
2. `business_error（业务错误）`
   - `QUOTA_EXCEEDED`
   - `RATE_LIMITED`
   - `USER_SUSPENDED`
3. `dependency_error（依赖错误）`
   - `MongoDB`
   - `Redis`
   - `provider`
   - `DashScope`
   - `DashVector`
4. `internal_error（内部错误）`
   - 未知异常
   - 代码 bug

### 5.2 建议统一错误码矩阵

生产收口后建议只保留这组对外错误码：

1. `AUTH_TOKEN_MISSING`
2. `AUTH_TOKEN_INVALID`
3. `AUTH_TOKEN_EXPIRED`
4. `LOGIN_SESSION_NOT_FOUND`
5. `LOGIN_SESSION_CONSUMED`
6. `USER_SUSPENDED`
7. `INVALID_CHAT_MESSAGES`
8. `INVALID_VECTORIZE_REQUEST`
9. `INVALID_RETRIEVAL_REQUEST`
10. `QUOTA_EXCEEDED`
11. `RATE_LIMITED`
12. `DEPENDENCY_UNAVAILABLE`
13. `PROVIDER_TRANSPORT_ERROR`
14. `MODEL_PROVIDER_INVALID_RESPONSE`
15. `PROVIDER_TIMEOUT`
16. `MODEL_PROVIDER_UNAVAILABLE`
17. `VECTOR_EMBEDDING_ERROR`
18. `VECTOR_DB_ERROR`
19. `SERVER_INTERNAL_ERROR`

### 5.3 依赖错误映射

#### MongoDB

1. 启动期 `ensure_connection()` 失败
   - 归类：`DEPENDENCY_UNAVAILABLE`
   - 行为：`readiness fail（就绪失败）`
   - 降级：生产环境不允许自动降级到 `in-memory`
2. 运行期读写失败
   - 归类：`DEPENDENCY_UNAVAILABLE`
   - 行为：返回 `503`
   - 日志：记录 `collection / operation / request_id`

#### Redis

1. 启动期失败
   - 归类：`DEPENDENCY_UNAVAILABLE`
   - 行为：`readiness fail`
2. 运行期失败
   - 开发环境：允许降级到 `memory counter`
   - 生产环境：默认不降级，直接 `503`
   - 原因：生产环境若悄悄降级，会导致多实例 `rate limit` 失真

#### Chat Provider

1. 上游 `429`
   - 对外：`429 RATE_LIMITED`
   - 同时记录 `provider_rate_limit`
2. 上游 `5xx / invalid body / invalid chunk`
   - 对外：`502 MODEL_PROVIDER_UNAVAILABLE`
3. 超时
   - 对外：`504` 或统一 `502`
   - 建议：显式增加 `PROVIDER_TIMEOUT`

#### DashScope / DashVector

1. 配置缺失
   - 对外：`503 VECTOR_CONFIG_ERROR`
2. 模型调用失败
   - 对外：`502 VECTOR_EMBEDDING_ERROR`
3. 向量库写入/检索失败
   - 对外：`502 VECTOR_DB_ERROR`

### 5.4 生产降级矩阵

| 依赖 | 开发环境 | 预发环境 | 生产环境 |
| --- | --- | --- | --- |
| `MongoDB` | 可降级到 `in-memory` | 不建议 | 禁止 |
| `Redis` | 可降级到 `memory counter` | 不建议 | 禁止 |
| `Chat provider` | 返回错误即可 | 返回错误 | 返回错误 |
| `DashScope` | 返回错误 | 返回错误 | 返回错误 |
| `DashVector` | 返回错误 | 返回错误 | 返回错误 |

建议新增环境开关：

1. `APP_ENV=local|staging|production`
2. `ALLOW_INMEMORY_MONGO_FALLBACK=false`
3. `ALLOW_INMEMORY_REDIS_FALLBACK=false`

收口原则：

1. `fallback（降级）` 只用于开发提效，不用于生产掩盖故障
2. 生产环境只允许“快速失败 + 明确告警”

## 6. Workstream C：安全收尾

### 6.1 .env 密钥治理

当前需要收口的问题：

1. [server/app/config.py](/home/sherwen/MyProjects/Entrocut_server/server/app/config.py) 里仍有开发默认 `AUTH_JWT_SECRET`
2. [server/.env.example](/home/sherwen/MyProjects/Entrocut_server/server/.env.example) 还没有区分生产必填项
3. `GOOGLE_API_KEY / DASHSCOPE_API_KEY / DASHVECTOR_API_KEY / MONGODB_URI` 都属于高敏感密钥

建议动作：

1. 新增 `server/.env.production.example`
2. `AUTH_JWT_SECRET` 改为无默认值，启动时强校验
3. 新增启动校验：
   - 缺少生产必填密钥时直接拒绝启动
4. 统一密钥来源：
   - 本地开发：`.env`
   - 预发/生产：云平台 `Secret Manager（密钥管理）`
5. 补一份“密钥轮换清单”

生产必填：

1. `AUTH_JWT_SECRET`
2. `MONGODB_URI`
3. `REDIS_URL`
4. `GOOGLE_API_KEY` 或其它 `LLM provider key`
5. `DASHSCOPE_API_KEY`
6. `DASHVECTOR_API_KEY`
7. `DASHVECTOR_ENDPOINT`
8. `AUTH_GOOGLE_CLIENT_ID`
9. `AUTH_GOOGLE_CLIENT_SECRET`

### 6.2 CORS 白名单

当前 [server/app/config.py](/home/sherwen/MyProjects/Entrocut_server/server/app/config.py) 已经改为白名单模式，但还需要生产收口：

1. 本地开发白名单与生产白名单分离
2. 生产只允许正式 `web origin`
3. 禁止 `*`
4. 对 `allow_credentials=True` 继续保持严格白名单

建议：

1. `CORS_ALLOW_ORIGINS` 改为环境级配置
2. 启动时校验：生产环境若为空或含 `localhost`，直接拒绝启动

### 6.3 Dev Fallback（开发回流页）

当前 `auth_dev_fallback_enabled=true` 只适合开发。

建议：

1. 生产默认强制 `false`
2. 生产环境若该值为 `true`，启动拒绝
3. 在 `/api/v1/runtime/capabilities` 或 `/health` 中体现 `dev fallback enabled` 状态

### 6.4 限额与限流校准

当前默认值：

1. `quota_free_total_tokens=200_000`
2. `rate_limit_requests_per_minute=20`
3. `rate_limit_tokens_per_minute=40_000`

这组值适合开发，不一定适合线上。

建议按环境拆分：

1. `free`
2. `trial`
3. `paid`
4. `internal`

首版可先保持单一计划，但要把配置抽成：

1. `chat_rpm`
2. `chat_tpm`
3. `daily_quota`
4. `monthly_quota`

同时增加两类保护：

1. 单请求最大 `prompt token` 保护
2. 单请求最大 `completion token` 保护

## 7. Workstream D：部署前改造清单

### P0

1. 统一 `structured logging`
2. 增加 `/metrics`
3. 增加 `readiness / liveness`
4. 增加 `APP_ENV`
5. 禁止生产环境 `MongoDB/Redis fallback`
6. 禁止生产环境默认密钥
7. 禁止生产环境 `dev fallback`
8. 收口 `provider timeout / connection error / invalid chunk` 错误码

### P1

1. 补告警规则
2. 补 `runbook（运行手册）`
3. 为 `chat/vector/auth` 增加关键日志字段
4. 为 `quota / rate limit` 增加指标

### P2

1. 补 `audit log（审计日志）`
2. 补更细的 `plan-based quota（按套餐额度）`
3. 补 `provider routing strategy（上游路由策略）`

## 8. 部署前验收标准

### 功能

1. 全量 `server/tests` 通过
2. 登录、刷新、登出、`client -> core token sync` 回归通过
3. `chat` 非流式与流式都通过真实上游
4. `/v1/assets/vectorize` 与 `/v1/assets/retrieval` 通过真实云端

### 可观测性

1. 任意请求都能按 `request_id` 查全链路日志
2. `/metrics` 可被监控系统抓取
3. 至少能看到 `p50/p95 latency`、`5xx count`、`provider error count`

### 安全

1. 生产无默认密钥
2. 生产无 `localhost` CORS
3. 生产无 `dev fallback`
4. 日志中不出现敏感密钥或 token

### 韧性

1. `MongoDB` 断开时 `readiness fail`
2. `Redis` 断开时 `readiness fail`
3. `provider` 超时与错误能稳定映射为预期错误码
4. 不依赖隐式 `fallback` 掩盖生产故障

## 9. 推荐落地顺序

1. 先做 `APP_ENV + 启动校验 + fallback 禁止`
2. 再做 `structured logging`
3. 再做 `/metrics`
4. 再做错误分级统一与超时/连接错误映射
5. 最后补告警规则、运行手册、生产配置模板

这条顺序的原因很直接：先把“不能带病上线”的硬门槛卡住，再补排障能力，最后补监控与文档。
