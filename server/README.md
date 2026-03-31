# Server

`server` 现在已经不只是 `auth phase 1`，而是进入了“鉴权主链已打通、云端网关逐步收口”的阶段。

## 当前定位

`server` 的角色不是本地剪辑引擎，而是 `Core -> Server` 的云端能力网关，当前重点有三条：

1. `Authentication / Authorization（认证 / 授权）`
2. `OpenAI-compatible chat proxy（兼容 OpenAI 的聊天代理）`
3. 为后续 `credits / BYOK / retrieval / inspect` 保留稳定扩展点

## 当前已落地能力

### 鉴权与用户链路

1. `POST /api/v1/auth/login-sessions`
2. `GET /api/v1/auth/oauth/google/start`
3. `GET /api/v1/auth/oauth/google/callback`
4. `GET /api/v1/auth/oauth/github/start`
5. `GET /api/v1/auth/oauth/github/callback`
6. `GET /api/v1/auth/login-sessions/{id}`
7. `POST /api/v1/auth/refresh`
8. `POST /api/v1/auth/logout`
9. `GET /api/v1/me`

### 云端网关与运行态

1. `POST /v1/chat/completions`
2. `GET /health`
3. `GET /api/v1/runtime/capabilities`
4. `GET /`

### 当前分支已并入的能力线

1. `Google + GitHub OAuth`
2. `client -> core -> server` 登录态传递链
3. `credits_balance` 用户字段及前端展示入口
4. `model selection + BYOK routing` 配套参数透传

## 当前约束与运行说明

1. `Google OAuth` 需要配置 `AUTH_GOOGLE_CLIENT_ID / AUTH_GOOGLE_CLIENT_SECRET`
2. `GitHub OAuth` 需要配置 `AUTH_GITHUB_CLIENT_ID / AUTH_GITHUB_CLIENT_SECRET`
3. `MongoDB Atlas` 未配置时，仓储层会退回进程内存模式，方便本地开发
4. `Redis` 不可用时，`login_session` 会退回进程内存模式，方便本地开发
5. `POST /v1/chat/completions` 当前主链已经受鉴权保护，但真实上游能力和计费闭环仍需继续验证

## 当前非目标

当前版本仍然**不追求**：

1. 复杂 `admin panel（管理后台）`
2. 团队级 `RBAC（基于角色的访问控制）`
3. 完整产品化的 `credits settlement（credits 结算）`
4. 生产级稳定的 `BYOK provider compatibility（BYOK 供应商兼容矩阵）`
5. 完整落地的 `retrieval / inspect / vectorize` 生产链路

## 现阶段最准确的理解

可以把当前 `server` 看成：

1. 鉴权底座已经成立
2. `chat proxy` 主链已经接上
3. 历史 `GitHub OAuth` 与 `credits/BYOK` 分支能力已经回收
4. 但仍需要继续补真实上游联调、计费回归和端到端测试
