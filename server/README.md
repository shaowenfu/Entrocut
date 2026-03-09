# Server Auth Phase 1

`server` 已从单文件 `skeleton（骨架）` 进入 `auth phase 1（鉴权一期）`。

## 当前定位

当前重点是先把 `Authentication（登录认证）` 底座搭起来，为后续 `chat proxy（模型中转）` 提供稳定身份链路。

## 当前能力

1. `GET /health`
2. `GET /api/v1/runtime/capabilities`
3. `POST /api/v1/auth/login-sessions`
4. `GET /api/v1/auth/oauth/google/start`
5. `GET /api/v1/auth/oauth/google/callback`
6. `GET /api/v1/auth/login-sessions/{id}`
7. `POST /api/v1/auth/refresh`
8. `POST /api/v1/auth/logout`
9. `GET /api/v1/me`
10. `GET /`

说明：

1. `Google OAuth` 需要在环境变量里配置 `AUTH_GOOGLE_CLIENT_ID / AUTH_GOOGLE_CLIENT_SECRET`
2. `MongoDB Atlas` 未配置时，仓储层会退回进程内存模式，方便本地开发
3. `Redis` 不可用时，`login_session` 会退回进程内存模式，方便本地开发

## 非目标

当前版本 **不包含**：

1. `GitHub OAuth`
2. 复杂 `admin panel（管理后台）`
3. 团队级 `RBAC（基于角色的访问控制）`
4. `LLM proxy（大模型中转）`
5. `Embedding proxy（向量化中转）`
6. `DashVector search（向量检索）`
7. `quota/rate limit（配额与限流）`

## 保留原因

1. 保留云端服务启动方式
2. 保留 `request_id（请求标识）` 中间件
3. 保留本地 `CORS（跨域）` 访问支持
4. 为下一轮接入 `chat proxy`、`quota`、`provider routing（供应商路由）` 提供稳定身份底座
