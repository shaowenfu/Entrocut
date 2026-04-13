# Server

`server` 现在已经不只是 `auth phase 1`，而是进入了“鉴权主链已打通、云端网关逐步收口”的阶段。

## 当前定位

`server` 的角色不是本地剪辑引擎，而是 `Core -> Server` 的云端能力网关，当前重点有三条：

1. `Authentication / Authorization（认证 / 授权）`
2. `OpenAI-compatible chat proxy（兼容 OpenAI 的聊天代理）`
3. 为后续 `credits / BYOK / retrieval / inspect` 保留稳定扩展点

## 文件目录体系

当前 `server` 方向建议按下面这条最小路径读：

1. `server/README.md`
   - `server` 当前定位、能力边界、阅读入口
2. `docs/server/README.md`
   - `server` 文档总索引，适合先看全局目录
3. `docs/server/01_server_module_design.md`
   - 模块边界与职责拆分
4. `docs/server/02_server_api_inventory.md`
   - 接口清单与 API 面收口
5. `docs/server/03_server_auth_system_design.md`
   - 鉴权、登录、用户链路
6. `docs/server/04_server_openai_compatible_contract.md`
   - `Core -> Server` 云端契约
7. `docs/server/05_auth_implementation_spec.md`
   - 已落地鉴权实现规范
8. `docs/server/06_server_vector_rag_design.md`
   - 向量、检索、`RAG（检索增强生成）`
9. `docs/server/06a_server_retrieve_inspect_gateway_design.md`
   - `retrieve / inspect` 网关方案
10. `docs/server/07_server_production_hardening_plan.md`
    - 生产加固
11. `docs/server/08_server_staging_runbook.md`
    - `staging（预发布）` 运维说明

代码侧建议重点看：

1. [`server/app/main.py`](./app/main.py)
   - 稳定入口，重新导出 `app` 与核心单例
2. [`server/app/bootstrap/dependencies.py`](./app/bootstrap/dependencies.py)
   - 依赖装配、运行态对象、健康探针
3. [`server/app/api/routes/auth.py`](./app/api/routes/auth.py)
   - OAuth、login session、refresh、logout、`me`
4. [`server/app/services/gateway/chat_proxy.py`](./app/services/gateway/chat_proxy.py)
   - `OpenAI-compatible chat proxy`
5. [`server/app/services/vector.py`](./app/services/vector.py)
   - `vectorize / retrieval`
6. [`server/app/services/inspect.py`](./app/services/inspect.py)
   - `inspect` 判定链
7. [`server/app/schemas/`](./app/schemas)
   - 请求 / 响应 `schema（模式）`

## 推荐代码阅读顺序

如果目标是先把 `server` 主链梳理清楚，建议按这个顺序读代码：

1. [`server/app/schemas/`](./app/schemas)
   - 先看请求和响应 `schema（模式）`
2. [`server/app/core/errors.py`](./app/core/errors.py)
   - 再看错误语义
3. [`server/app/services/auth/`](./app/services/auth)
   - 了解登录、token、用户如何成立
4. [`server/app/services/quota.py`](./app/services/quota.py)
   - 了解 `credits` 和限流如何介入主链
5. [`server/app/services/vector.py`](./app/services/vector.py)
   - 了解向量化与检索
6. [`server/app/services/inspect.py`](./app/services/inspect.py)
   - 了解候选精判
7. [`server/app/bootstrap/`](./app/bootstrap)
   - 最后串起路由、依赖注入、日志、指标和异常处理

如果只想快速抓主干，直接读 `server/app/bootstrap/dependencies.py`，再回头补 `services/gateway/chat_proxy.py` 和 `services/vector.py`。

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

## 开发辅助脚本

### `scripts/issue_super_token.py` — 签发开发用超级用户 token

用于在本地或 staging 环境快速获取一个长效 access token，跳过正常登录流程，方便调试鉴权保护下的 API。

**做了什么：**
1. 在 MongoDB 中创建（或复用）一个 `dev_superuser` 用户，自带极高 credits 余额
2. 创建一条对应的 login session
3. 签发一个有效期 100 年的 JWT，scope 包含 `user:read` 和 `chat:proxy`

**用法：**
```bash
# 使用默认 user-id / email
python scripts/issue_super_token.py

# 自定义
python scripts/issue_super_token.py --user-id myuser --email my@dev.local
```

输出可直接用作 `Authorization: Bearer <token>` 测试任意受保护端点。

> 仅限开发 / staging 使用，**禁止在生产环境运行**。

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
4. `core` 已开始在 agent loop 中真实调用 `POST /v1/assets/retrieval`
5. 仍需要继续补真实上游联调、计费回归和端到端测试
