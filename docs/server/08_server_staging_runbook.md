# Server 预发联调 Runbook（运行手册）

本文档面向 `staging（预发环境）` 联调。目标只有两个：

1. 快速确认 `server` 是否达到可接流量状态
2. 当联调失败时，能按固定顺序定位问题

## 1. 上线前检查

预发环境必须满足：

1. `APP_ENV=staging`
2. `AUTH_JWT_SECRET` 已替换正式强密钥
3. `AUTH_DEV_FALLBACK_ENABLED=false`
4. `ALLOW_INMEMORY_MONGO_FALLBACK=false`
5. `ALLOW_INMEMORY_REDIS_FALLBACK=false`
6. `CORS_ALLOW_ORIGINS` 不包含 `localhost` 或 `127.0.0.1`
7. `MONGODB_URI`、`REDIS_URL`、`GOOGLE_API_KEY`、`DASHSCOPE_API_KEY`、`DASHVECTOR_API_KEY`、`DASHVECTOR_ENDPOINT` 已配置
8. 若要跑自动化鉴权冒烟：`STAGING_TEST_BOOTSTRAP_ENABLED=true` 且 `STAGING_TEST_BOOTSTRAP_SECRET` 已配置

## 2. 启动后先看三类端点

### `GET /livez`

用途：只判断进程是否活着。

预期：

1. 返回 `200`
2. `status=ok`

### `GET /readyz`

用途：判断依赖是否就绪，是否可以接真实流量。

预期：

1. 返回 `200`
2. `status=ready`
3. `mongodb`、`redis`、`chat_provider` 至少应为 `ok=true`

若返回 `503`：

1. 先看 `dependencies` 里哪个依赖 `ok=false`
2. 再去日志里按 `request_id` 和 `dependency` 排查

### `GET /metrics`

用途：确认 `metrics（指标）` 暴露正常。

至少检查：

1. `server_http_requests_total`
2. `server_dependency_health`
3. `server_chat_requests_total`
4. `server_chat_provider_latency_ms_avg`

## 3. 预发联调命令

仓库根目录执行：

```bash
./scripts/staging_smoke_test.sh --server-base-url http://127.0.0.1:8001 --core-base-url http://127.0.0.1:8000 --bootstrap-secret <your-bootstrap-secret>
```

这条脚本会做：

1. `livez`
2. `readyz`
3. `metrics`
4. 复用现有 `auth/chat` 主链回归

## 4. 日志排查顺序

现在所有关键事件都有 `structured logging（结构化日志）`，优先按这些字段查：

1. `request_id`
2. `category=audit`
3. `action`
4. `user_id / actor_user_id`
5. `session_id / actor_session_id`
6. `dependency`
7. `error_code`

关键事件：

1. `auth_login_session_created`
2. `auth_oauth_callback_succeeded`
3. `auth_refresh_succeeded`
4. `auth_logout_succeeded`
5. `chat_request_started`
6. `chat_request_succeeded`
7. `chat_stream_completed`
8. `vectorize_started`
9. `vectorize_succeeded`
10. `retrieval_started`
11. `retrieval_succeeded`

关键 `audit` 动作：

1. `auth.login_session.create`
2. `auth.login_session.claim`
3. `auth.oauth.callback`
4. `auth.refresh`
5. `auth.logout`
6. `chat.completions.consume`
7. `chat.completions.stream.consume`
8. `assets.vectorize`
9. `assets.retrieval`

## 5. 常见故障与处理

### `readyz` 失败

1. `mongodb ok=false`
   - 检查 `MONGODB_URI`
   - 检查 Atlas 白名单和网络出口
2. `redis ok=false`
   - 检查 `REDIS_URL`
   - 检查实例连通性
3. `chat_provider ok=false`
   - 检查 `GOOGLE_API_KEY`
   - 检查 `LLM_PROXY_MODE`

### `chat` 返回 `504 PROVIDER_TIMEOUT`

1. 先看 `server_chat_provider_latency_ms`
2. 再看上游区域网络和 provider 状态
3. 若是偶发，先按预发告警阈值观察，不要直接放大超时阈值

### `chat` 返回 `502 PROVIDER_TRANSPORT_ERROR`

1. 多半是 DNS、TLS、出口网络或 provider 连接失败
2. 优先看 `dependency_error` 和 `server_chat_provider_errors_total`

### `chat` 返回 `502 MODEL_PROVIDER_INVALID_RESPONSE`

1. 说明上游返回体或流式 chunk 不符合预期
2. 先检查 provider 兼容层是否变更
3. 保留 `request_id` 和错误摘要，不要把完整响应体打入日志

### `vectorize/retrieval` 失败

1. `VECTOR_EMBEDDING_ERROR`
   - 看 `DASHSCOPE_API_KEY`
   - 看模型可用性
2. `VECTOR_DB_ERROR`
   - 看 `DASHVECTOR_ENDPOINT`
   - 看集合状态与权限

## 6. 联调通过标准

至少满足：

1. `./scripts/staging_smoke_test.sh` 返回 `0`
2. `/readyz` 连续 3 次为 `200`
3. `auth/chat` 主链回归通过
4. `request_id` 能串起日志与错误
5. `audit` 日志能看到登录、刷新、登出、额度扣减
