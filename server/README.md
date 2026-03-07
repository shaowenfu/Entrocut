# Server Skeleton

`server` 已进入 `clean-room rewrite（净室重构）` 阶段。

## 当前定位

`server` 现在只保留最小 `FastAPI（服务框架）` 壳，用来承接下一轮从零重建的 `auth/proxy（鉴权与中转）` 契约。

## 当前能力

1. `GET /health`
2. `GET /api/v1/runtime/capabilities`
3. `GET /`

## 非目标

当前版本 **不包含**：

1. `JWT auth（鉴权）`
2. `LLM proxy（大模型中转）`
3. `Embedding proxy（向量化中转）`
4. `DashVector search（向量检索）`
5. `jobs/queue（任务队列）`
6. `quota/rate limit（配额与限流）`

## 保留原因

1. 保留云端服务启动方式
2. 保留 `request_id（请求标识）` 中间件
3. 保留本地 `CORS（跨域）` 访问支持
4. 为下一轮重新定义 `auth + provider schema（鉴权与供应商契约）` 提供干净落点
