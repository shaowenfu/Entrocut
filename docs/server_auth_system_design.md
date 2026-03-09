# Server Auth System Design

本文档定义 `EntroCut server` 侧的 `Authentication（登录认证）`、`Registration（注册）`、`User Management（用户管理）`、`Authorization（访问授权）` 的完整开发方案。

目标不是做一个“大而全用户中心”，而是先搭一套小而完整、可扩展、适合桌面应用的鉴权系统，为后续 `chat proxy`、`embedding proxy`、`quota`、`project sync` 提供统一底座。

本文档与 [Server OpenAI-Compatible Contract](./server_openai_compatible_contract.md) 配套：

1. 本文档定义“用户怎么登录、token 怎么来、server 怎么认人”
2. `server_openai_compatible_contract.md` 定义“拿到 token 之后，Core 怎么调用受保护的 AI 接口”

## 1. 一句话结论

推荐方案：

`FastAPI + MongoDB Atlas + PyMongo + Authlib + PyJWT + Redis`

登录体验采用：

`Electron client` 打开系统浏览器完成 `OAuth`，`server` 回调后签发 EntroCut 自己的 `access token + refresh token`，再通过 `Custom URI Scheme（自定义协议）` 或降级方案把登录结果带回桌面应用。

## 2. 目标与非目标

### 2.1 当前目标

首期鉴权系统必须支持：

1. `Google OAuth` 登录
2. `GitHub OAuth` 登录
3. 首次 `OAuth` 登录自动注册
4. `access token / refresh token` 双令牌体系
5. `GET /api/v1/me` 查询当前用户
6. 基于用户身份保护后续 `chat proxy` 等接口
7. 支持桌面应用登录回调与失败兜底
8. 用户状态、套餐、额度、项目归属可落在我们自己的数据库里

### 2.2 当前非目标

当前版本不做：

1. 完整 `admin panel（管理后台）`
2. 复杂组织体系、团队空间、细粒度 `RBAC（基于角色的访问控制）`
3. `Email + Password` 登录
4. `Email magic link` 登录
5. 多因素认证
6. 风控评分系统
7. 账户合并自动化

这些都可以后续扩展，但不应该阻塞第一版上线。

## 3. 为什么这样设计

我们当前面对的是桌面产品，不是纯网页产品。

所以登录方案必须满足四件事：

1. 用户不在应用内输入第三方账号密码
2. 应用端不直接持有 `Google/GitHub` 的长期凭证
3. `Core` 与 `Server` 的内部通信只认 EntroCut 自己的 `JWT`
4. 后续套餐、额度、项目权限必须由我们自己控制

因此系统必须拆成两层：

1. `Identity（身份）`
   由 `Google/GitHub` 证明“这个人是谁”
2. `Entitlement（产品权限）`
   由 EntroCut 自己决定“这个人在系统里是谁、能做什么、还有多少额度”

这也是为什么第三方登录只负责认证，不负责我们产品内的权限判断。

## 4. 技术栈选择

### 4.1 `FastAPI`

继续使用 `FastAPI`，原因：

1. 当前 `server` 已是 Python 主栈
2. 后续 `auth middleware`、`chat proxy`、`SSE` 可以共用同一进程
3. 团队无需额外引入新的后端语言和部署形态

### 4.2 `MongoDB Atlas`

作为主数据库，原因：

1. 你已经明确希望使用 `MongoDB Atlas`
2. `users / auth_identities / refresh_tokens / quota_ledgers` 非常适合文档模型
3. 早期结构可能演进较快，文档库迁移成本更低

### 4.3 `PyMongo`

第一版优先直接使用 `PyMongo`，不急着上 `ODM`

原因：

1. 鉴权模型不复杂
2. 直接操作集合更透明
3. 避免被 `ODM` 绑定和抽象层限制

### 4.4 `Authlib`

用于实现 `OAuth 2.0 / OIDC`

原因：

1. 不需要自己手搓 `OAuth` 协议细节
2. 适合接 `Google` 和 `GitHub`
3. 与 Python / ASGI 栈适配成熟

### 4.5 `PyJWT`

用于签发 EntroCut 自己的 `JWT`

原因：

1. 当前项目依赖里已经有
2. 访问控制面不需要引入更重的鉴权框架

### 4.6 `Redis`

用于短期状态存储：

1. `OAuth state`
2. `PKCE verifier`
3. 临时登录会话
4. 登录轮询状态
5. 限流桶

如果第一版极简，也可先只用于 `state` 和登录轮询，但后续 `rate limit` 基本仍需要它。

## 5. 系统边界

### 5.1 `client`

负责：

1. 展示登录入口
2. 打开系统浏览器
3. 接收回调结果
4. 存储 EntroCut 的 `access token / refresh token`
5. 将 `access token` 传给 `core`

### 5.2 `core`

负责：

1. 保存当前登录态
2. 调用受保护的 `server` 接口时携带 `Authorization: Bearer <access_token>`
3. 处理 `401 / 402 / 429` 等错误并通知前端

`Core` 不负责：

1. 第三方登录流程
2. 刷新令牌签发
3. 用户权限管理

### 5.3 `server`

负责：

1. 启动 `OAuth` 流程
2. 处理 `Google/GitHub callback`
3. 创建/查询本地用户
4. 签发 `access token / refresh token`
5. 提供 `me / logout / refresh`
6. 鉴权中间件
7. 用户状态、套餐、额度、项目归属

## 6. 总体登录流程

### 6.1 标准成功链路

1. 用户在 `Electron client` 点击“Continue with Google”
2. `client` 打开系统浏览器访问：
   `GET /api/v1/auth/oauth/google/start`
3. `server` 生成 `state + PKCE verifier/challenge + login_session_id`
4. `server` 将浏览器 `302 redirect` 到 `Google authorize URL`
5. 用户在浏览器内完成 `Google` 登录和授权
6. `Google` 回调：
   `GET /api/v1/auth/oauth/google/callback?code=...&state=...`
7. `server` 校验 `state`，再用 `code` 换取第三方 token
8. `server` 读取第三方用户资料
9. `server` 在 `MongoDB Atlas` 中查找或创建本地用户
10. `server` 签发 EntroCut 自己的 `access token + refresh token`
11. `server` 跳转到：
   `entrocut://auth/callback?...`
12. `Electron client` 接收深链接，保存 token
13. `client` 将 `access token` 同步给 `core`
14. `core` 后续请求 `server` 时携带 `Authorization: Bearer <access_token>`

### 6.2 登录失败兜底

如果 `Custom URI Scheme` 回调失败，降级到以下方案之一：

1. 浏览器展示一次性 `login code`
2. `client` 轮询 `server` 登录会话状态

推荐优先支持第二种：

浏览器回调成功后，`server` 将登录结果写入临时 `login_session`，`client` 轮询 `/api/v1/auth/login-sessions/{id}` 获取结果。

这样即使深链接被安全软件或系统配置拦截，也能继续完成登录。

## 7. 桌面应用回调方案

### 7.1 主方案：`Custom URI Scheme`

例如：

`entrocut://auth/callback?login_session_id=xxx`

优点：

1. 体验像 `Cursor / TRAE`
2. 更像原生桌面应用
3. 浏览器登录后可以自动拉回应用

风险：

1. 协议注册失败
2. 被系统策略或安全软件拦截
3. 本地开发和正式安装的协议处理需要分别调试

### 7.2 降级方案：登录轮询

流程：

1. `client` 打开浏览器前先创建一个 `login_session_id`
2. 浏览器登录完成后，`server` 将结果写入 `Redis`
3. `client` 每隔 1-2 秒轮询：
   `GET /api/v1/auth/login-sessions/{login_session_id}`
4. 轮询到成功后保存 token

优点：

1. 不依赖深链接一定成功
2. 对防火墙和协议注册问题更稳

缺点：

1. 体验略差
2. 需要额外临时状态存储

推荐策略：

1. 正常路径优先走 `Custom URI Scheme`
2. 始终保留登录轮询兜底

## 8. OAuth Provider 选择

第一版建议只接：

1. `Google`
2. `GitHub`

原因：

1. 主流开发者和创作者已有账号
2. `OAuth` 基础登录能力通常免费
3. 文档成熟、生态成熟

是否要“使用 Google/GitHub 的服务”：

是，要使用它们的 `OAuth` 授权服务，但通常不会因为普通登录功能单独收费。

## 9. 令牌体系设计

### 9.1 为什么不能只发一个长期 JWT

如果只发一个 7 天或 30 天超长有效期 `JWT`：

1. 一旦泄露，风险窗口太大
2. 很难安全登出
3. 难以做设备级撤销

所以必须分成：

1. `access token`
2. `refresh token`

### 9.2 `access token`

用途：

1. 给 `client / core` 请求 `server` 时放在 `Authorization` 头里

建议：

1. 有效期 15 分钟到 1 小时
2. 使用 `JWT`
3. 包含最小必要声明

推荐声明：

```json
{
  "sub": "user_123",
  "sid": "session_123",
  "scope": ["chat:proxy", "user:read"],
  "iat": 1700000000,
  "exp": 1700003600,
  "iss": "entrocut-server",
  "aud": "entrocut-core"
}
```

### 9.3 `refresh token`

用途：

1. 换取新的 `access token`
2. 支持长时间保持登录态

建议：

1. 使用高熵随机字符串，不要求必须是 `JWT`
2. 服务端只保存其哈希值
3. 有效期 30-90 天
4. 支持撤销
5. 每次刷新可选择做 `rotation（轮换）`

推荐做法：

1. `refresh token` 返回给客户端明文
2. 数据库只存 `sha256(refresh_token)`
3. 刷新成功后轮换为新 `refresh token`

### 9.4 Token 存储位置

`client` 端建议：

1. `access token` 放内存或安全存储
2. `refresh token` 放系统安全存储，例如 `keychain / credential manager`

当前如果先极简实现，也可以本地持久化，但要明确这是过渡方案。

## 10. 数据模型设计

基于 `MongoDB Atlas`，首期建议以下集合。

### 10.1 `users`

用于存产品内用户。

示例：

```json
{
  "_id": "user_123",
  "email": "alice@example.com",
  "display_name": "Alice",
  "avatar_url": "https://...",
  "status": "active",
  "primary_provider": "google",
  "created_at": "2026-03-08T10:00:00Z",
  "updated_at": "2026-03-08T10:00:00Z",
  "last_login_at": "2026-03-08T10:00:00Z"
}
```

规则：

1. `status` 至少支持：`active`、`suspended`、`deleted`
2. `email` 建议唯一索引
3. 即使未来允许匿名或无邮箱，也不要把第三方身份直接当主用户表

### 10.2 `auth_identities`

用于存第三方身份映射。

示例：

```json
{
  "_id": "identity_123",
  "user_id": "user_123",
  "provider": "google",
  "provider_user_id": "google_sub_abc",
  "provider_email": "alice@example.com",
  "provider_profile": {
    "name": "Alice",
    "avatar_url": "https://..."
  },
  "created_at": "2026-03-08T10:00:00Z",
  "updated_at": "2026-03-08T10:00:00Z"
}
```

规则：

1. `(provider, provider_user_id)` 必须唯一
2. 一个 `user` 可绑定多个 `identity`
3. 不要把第三方 `access token` 长期存库，除非有明确业务需要

### 10.3 `auth_sessions`

用于存应用登录会话。

示例：

```json
{
  "_id": "session_123",
  "user_id": "user_123",
  "client_type": "electron",
  "device_label": "Alice MacBook",
  "status": "active",
  "created_at": "2026-03-08T10:00:00Z",
  "last_seen_at": "2026-03-08T10:05:00Z",
  "revoked_at": null
}
```

作用：

1. 支持多设备登录
2. 支持退出当前设备
3. 支持未来“查看登录设备”

### 10.4 `refresh_tokens`

用于存刷新令牌。

示例：

```json
{
  "_id": "rt_123",
  "session_id": "session_123",
  "user_id": "user_123",
  "token_hash": "sha256_xxx",
  "expires_at": "2026-04-08T10:00:00Z",
  "rotated_from": null,
  "revoked_at": null,
  "created_at": "2026-03-08T10:00:00Z"
}
```

规则：

1. 只存哈希，不存明文
2. 支持轮换和撤销

### 10.5 `login_sessions`

用于存一次浏览器登录过程的临时状态，建议放 `Redis`。

字段建议：

```json
{
  "login_session_id": "login_123",
  "provider": "google",
  "status": "pending",
  "state": "random_state",
  "pkce_verifier": "random_verifier",
  "client_redirect_uri": "entrocut://auth/callback",
  "result": null,
  "expires_at": "2026-03-08T10:10:00Z"
}
```

状态流转：

1. `pending`
2. `authenticated`
3. `failed`
4. `expired`

### 10.6 未来业务集合

本文档不展开，但应预留：

1. `subscriptions`
2. `quota_ledgers`
3. `projects`
4. `project_members`

## 11. API 设计

首期建议暴露以下接口。

### 11.1 `POST /api/v1/auth/login-sessions`

用途：

1. 由 `client` 创建一次桌面登录会话

请求：

```json
{
  "provider": "google",
  "client_redirect_uri": "entrocut://auth/callback"
}
```

响应：

```json
{
  "login_session_id": "login_123",
  "authorize_url": "https://api.entrocut.com/api/v1/auth/oauth/google/start?login_session_id=login_123"
}
```

### 11.2 `GET /api/v1/auth/oauth/{provider}/start`

用途：

1. 创建 `state / PKCE`
2. 跳转到第三方授权页

输入：

1. `provider`
2. `login_session_id`

行为：

1. 校验 `login_session`
2. 生成 `state`
3. 保存 `state -> login_session` 映射
4. `302 redirect` 到第三方授权地址

### 11.3 `GET /api/v1/auth/oauth/{provider}/callback`

用途：

1. 处理第三方回调
2. 创建或查找本地用户
3. 签发 EntroCut token
4. 更新 `login_session` 状态
5. 跳回应用或展示兜底页

### 11.4 `GET /api/v1/auth/login-sessions/{id}`

用途：

1. 给桌面应用轮询登录结果

响应示例：

```json
{
  "login_session_id": "login_123",
  "status": "authenticated",
  "result": {
    "access_token": "jwt_xxx",
    "refresh_token": "rt_xxx",
    "expires_in": 3600,
    "user": {
      "id": "user_123",
      "email": "alice@example.com",
      "display_name": "Alice",
      "avatar_url": "https://..."
    }
  }
}
```

安全要求：

1. 登录结果一旦被客户端成功领取，应立即失效或置为已消费
2. 结果 TTL 必须很短

### 11.5 `POST /api/v1/auth/refresh`

用途：

1. 用 `refresh token` 换新 `access token`

请求：

```json
{
  "refresh_token": "rt_xxx"
}
```

响应：

```json
{
  "access_token": "jwt_new",
  "refresh_token": "rt_new",
  "expires_in": 3600
}
```

规则：

1. 校验哈希
2. 检查是否过期或撤销
3. 建议执行轮换

### 11.6 `POST /api/v1/auth/logout`

用途：

1. 撤销当前会话

请求可用：

1. 当前 `access token`
2. 或 `refresh token`

行为：

1. 撤销当前 `session`
2. 撤销该 `session` 下所有可用 `refresh token`

### 11.7 `GET /api/v1/me`

用途：

1. 返回当前登录用户资料

响应示例：

```json
{
  "user": {
    "id": "user_123",
    "email": "alice@example.com",
    "display_name": "Alice",
    "avatar_url": "https://...",
    "status": "active",
    "plan": "free",
    "quota_status": "healthy"
  }
}
```

### 11.8 `PATCH /api/v1/me`

首期只允许修改最小字段：

1. `display_name`
2. `avatar_url`

不要一开始做复杂资料编辑系统。

## 12. 注册策略

在这套方案里，“注册”不是一个独立大表单页面，而是：

首次 `OAuth` 成功登录时自动注册。

规则：

1. 如果 `(provider, provider_user_id)` 已存在，则直接登录
2. 如果不存在，则尝试按 `email` 查找已有用户
3. 若邮箱存在且允许绑定，则挂接新的 `identity`
4. 若邮箱不存在，则创建新用户

关于“是否允许自动按邮箱合并账号”，建议第一版保守处理：

1. 同邮箱自动绑定只在你明确接受风险时启用
2. 更稳妥的方式是先仅按 `(provider, provider_user_id)` 唯一

## 13. 用户管理设计

### 13.1 用户状态

最少定义：

1. `active`
2. `suspended`
3. `deleted`

行为：

1. `active` 可正常使用
2. `suspended` 登录成功后也不能继续使用受保护接口
3. `deleted` 逻辑删除，保留审计信息

### 13.2 用户对产品能力的关系

用户管理不能只停在“能不能登录”，还要落到产品权限：

1. 这个用户属于哪个套餐
2. 这个用户还有多少额度
3. 这个用户可访问哪些项目

所以 `auth` 不是孤立模块，而是整个 `server` 权限体系入口。

### 13.3 当前 `me` 视图建议

前端当前真会用到的字段只保留：

1. `id`
2. `email`
3. `display_name`
4. `avatar_url`
5. `status`
6. `plan`
7. `quota_status`

## 14. 鉴权中间件设计

所有受保护接口统一走 `auth middleware` 或 `dependency`

能力要求：

1. 解析 `Authorization: Bearer <access_token>`
2. 校验签名、过期时间、`iss`、`aud`
3. 读取 `sub`、`sid`
4. 加载当前用户
5. 检查用户状态
6. 将 `current_user`、`current_session` 注入请求上下文

受保护接口包括：

1. `GET /api/v1/me`
2. `PATCH /api/v1/me`
3. `POST /v1/chat/completions`
4. 后续 `embeddings / search / quota / project sync`

## 15. OAuth 关键安全要求

### 15.1 必须使用 `Authorization Code Flow + PKCE`

不要使用简化流。

### 15.2 必须校验 `state`

否则会有 `CSRF（跨站请求伪造）` 风险。

### 15.3 不信任前端传来的用户资料

用户身份信息必须来自第三方回调后的服务端拉取结果。

### 15.4 第三方 token 不直接下发给客户端

客户端和 `core` 只认 EntroCut 自己签发的 token。

### 15.5 `refresh token` 只存哈希

数据库泄露时能降低风险。

### 15.6 深链接不要直接携带长期敏感信息

更稳妥的做法是：

1. 深链接只带 `login_session_id`
2. 客户端再向 `server` 领取 token

这样比把 `access_token` 直接塞进 `entrocut://...` 更安全。

## 16. Electron 端集成建议

### 16.1 登录入口

`client` 点击按钮后：

1. 调 `POST /api/v1/auth/login-sessions`
2. 获取 `authorize_url`
3. 用系统浏览器打开 `authorize_url`
4. 启动深链接监听和登录轮询

### 16.2 回调接收

推荐：

1. 深链接只接收 `login_session_id`
2. 收到后调用 `GET /api/v1/auth/login-sessions/{id}`
3. 获取实际 token

### 16.3 本地存储

首期可简化，但建议目标形态是：

1. `refresh token` 放系统安全存储
2. `access token` 放内存
3. 应用启动时自动尝试刷新

## 17. 运行时配置

建议在 `server` 配置中增加：

```env
SERVER_BASE_URL=https://api.entrocut.com
AUTH_JWT_ALGORITHM=HS256
AUTH_JWT_SECRET=change-me
AUTH_ACCESS_TOKEN_EXPIRES_SECONDS=3600
AUTH_REFRESH_TOKEN_EXPIRES_SECONDS=2592000
AUTH_GOOGLE_CLIENT_ID=xxx
AUTH_GOOGLE_CLIENT_SECRET=xxx
AUTH_GITHUB_CLIENT_ID=xxx
AUTH_GITHUB_CLIENT_SECRET=xxx
AUTH_DEEP_LINK_SCHEME=entrocut
MONGODB_URI=mongodb+srv://...
REDIS_URL=redis://127.0.0.1:6379/0
```

说明：

1. 本地开发与生产的 `SERVER_BASE_URL`、`OAuth callback URL` 必须分开配置
2. `Google/GitHub` 的控制台里也要分别配置开发和生产回调地址

## 18. 推荐目录结构

建议在 `server/` 下逐步拆成：

```text
server/
  app/
    main.py
    config.py
    deps/
      auth.py
    routers/
      auth.py
      users.py
      chat_proxy.py
    services/
      oauth_service.py
      token_service.py
      user_service.py
      login_session_service.py
    repositories/
      users.py
      auth_identities.py
      sessions.py
      refresh_tokens.py
    models/
      auth.py
      user.py
    middleware/
      request_context.py
```

原则：

1. 路由层只处理 `HTTP`
2. 服务层处理业务
3. 仓储层处理 `MongoDB / Redis`

## 19. 分阶段实施计划

### Phase 1：打通最短登录闭环

目标：

1. `Google OAuth`
2. `login_session`
3. `callback`
4. 本地用户创建
5. `access token / refresh token`
6. `GET /api/v1/me`

先不做：

1. `GitHub`
2. 账号绑定
3. 设备管理页面

### Phase 2：完善会话和退出

目标：

1. `POST /api/v1/auth/refresh`
2. `POST /api/v1/auth/logout`
3. `auth_sessions`
4. `refresh token rotation`

### Phase 3：接入受保护业务接口

目标：

1. `POST /v1/chat/completions` 强制鉴权
2. 用户状态校验
3. 套餐与额度校验

### Phase 4：补 GitHub 和用户资料管理

目标：

1. `GitHub OAuth`
2. `PATCH /api/v1/me`
3. 多身份绑定策略

## 20. 测试重点

必须覆盖：

1. `state` 校验成功/失败
2. `PKCE` 正常工作
3. 首次登录自动注册
4. 重复登录命中已有用户
5. `refresh token` 轮换
6. 登出后 token 失效
7. `suspended user` 被禁止访问
8. 深链接失败时轮询兜底可用

## 21. 运行与联调流程

开发阶段建议流程：

1. 启动 `MongoDB Atlas` 连接
2. 启动本地 `Redis`
3. 启动 `server`
4. 在 `Google/GitHub OAuth app` 中配置本地回调地址
5. `client` 发起登录
6. 浏览器完成授权
7. `client` 通过深链接或轮询取回 token
8. 调 `GET /api/v1/me` 验证登录态
9. 调受保护的 `chat proxy` 验证鉴权中间件

## 22. 和 AI Proxy Contract 的对齐要求

后续所有受保护的 `AI proxy` 接口统一依赖本系统签发的 `access token`。

因此：

1. `Core` 请求 `POST /v1/chat/completions` 时带的不是第三方 token
2. 带的是 EntroCut 自己的 `access token`
3. `server` 在通过鉴权后，才内部注入真实 `provider credential`

这条边界不能混淆。

## 23. 最终判断

这套方案的核心不是“做一个登录页”，而是建立一条稳定的身份链路：

1. 第三方 `OAuth` 负责证明身份
2. EntroCut `server` 负责建立本地用户与权限
3. EntroCut 自己签发 token
4. `client / core` 只消费 EntroCut token
5. 所有后续 `chat / embeddings / search / sync` 都建立在这条身份链路之上

如果这条底座搭对了，后面的 `quota`、`billing`、`project sharing`、`team workspace` 都会顺很多；如果这里混乱，后面几乎每条业务线都会返工。
