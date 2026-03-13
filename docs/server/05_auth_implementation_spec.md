# Auth Implementation Spec

本文档定义当前 `EntroCut` 已落地的鉴权规范，供 `client / core / server` 工程师直接参考。

它不是愿景文档，而是当前代码实现的基线说明。

配套文档：

1. [Server Auth System Design](./03_server_auth_system_design.md)
2. [Server OpenAI-Compatible Contract](./04_server_openai_compatible_contract.md)
3. [Core API / WS Contract](../contracts/01_core_api_ws_contract.md)

## 1. 一句话结论

当前鉴权链路是：

`Google OAuth -> Server callback -> EntroCut JWT -> Client 保存登录态 -> Client 同步 access token 给 Core -> Core 带 Bearer token 调 Server`

系统分工固定为：

1. `client`
   负责登录入口、登录结果接收、本地 token 存储、把 token 同步给 `core`
2. `core`
   负责保存当前本地会话，并在调用云端 `server` 时自动带上 `Authorization`
3. `server`
   负责 `OAuth`、用户识别、`JWT` 签发、会话校验、受保护 AI 接口

## 2. 设计原则

### 2.1 内外字段分离

服务内部统一使用存储模型字段：

1. 用户主键使用 `_id`
2. 会话主键使用 `_id`
3. `refresh token`、`identity` 等内部文档同理

对外响应才映射成 API 字段：

1. 用户响应使用 `id`
2. 不向外暴露 `_id`

规则：

1. `server` 内部逻辑禁止混用 `_id` 和 `id`
2. 存储层对象进入 API 响应前必须先过映射函数
3. 契约层 JSON 不应出现 MongoDB 风格内部字段

### 2.2 登录和权限解耦

第三方 `OAuth` 只负责证明“你是谁”。

EntroCut 自己的 `JWT` 才表示：

1. 你在 EntroCut 里是谁
2. 当前会话是否有效
3. 是否允许访问 `chat proxy`

### 2.3 Token 不跨边界滥传

规则：

1. `Google token` 不进入 `client -> core -> server` 内部链路
2. `deep link` 不直接携带 `access token / refresh token`
3. `client` 只通过一次性 `login_session_id` 领取登录结果
4. `core` 只持有 EntroCut 自己的 `access token`

## 3. 当前实现总览

### 3.1 登录成功链路

1. `client` 调 `POST /api/v1/auth/login-sessions`
2. `server` 返回 `login_session_id + authorize_url`
3. 浏览器打开 `authorize_url`
4. `Google OAuth` 完成后回调 `server`
5. `server` 查找或创建本地用户
6. `server` 签发 EntroCut `access token + refresh token`
7. `server` 把结果写入 `login_session`
8. `client` 通过 `login_session_id` 一次性领取结果
9. `client` 保存本地 token
10. `client` 调本地 `core /api/v1/auth/session` 同步 `access token`
11. `core` 后续调用 `server` 时携带 `Authorization: Bearer <access_token>`

### 3.2 当前回流方式

桌面环境：

1. 优先走 `entrocut://auth/callback?...`

开发环境：

1. 允许 `server` 使用 `dev fallback page`
2. `fallback` 页面自动跳回前端页面
3. 前端再用 `auth_login_session_id` 自动领取登录结果

## 4. Token 体系

### 4.1 Access Token

定义：

1. `JWT`
2. 由 `server` 签发
3. 短生命周期
4. 用于访问 `GET /api/v1/me`、`POST /v1/chat/completions` 等受保护接口

当前载荷包含：

1. `sub`
   用户 `_id`
2. `sid`
   服务端会话 `_id`
3. `scope`
4. `iat`
5. `exp`
6. `iss`
7. `aud`

### 4.2 Refresh Token

定义：

1. 随机字符串，不是 `JWT`
2. 服务端存哈希
3. 用于换发新的 `access token`

规则：

1. `logout` 时会撤销该会话下的 `refresh token`
2. 已撤销或过期的 `refresh token` 必须返回 `401`

## 5. Client 规范

### 5.1 Client 必须负责的事情

1. 发起登录
2. 保存 `access token`
3. 保存 `refresh token`
4. 登录成功后同步 `access token` 给 `core`
5. 刷新成功后再次同步最新 `access token` 给 `core`
6. 登出后通知 `core` 清空本地会话

### 5.2 Client 本地存储

当前实现：

1. `access token`
   存在前端本地存储
2. `refresh token`
   存在前端本地存储

注意：

1. 这是当前开发阶段实现
2. 如果后续需要更强安全性，再考虑 OS 级安全存储

### 5.3 Client 刷新策略

当前策略：

1. `client` 负责刷新
2. `core` 不自己使用 `refresh token`
3. `core` 只消费最新同步过来的 `access token`

这是故意的职责分离，避免 `client` 和 `core` 双写刷新逻辑。

## 6. Core 规范

### 6.1 Core 的角色

`core` 不是登录入口，而是本地受控执行者。

它只做两件事：

1. 保存当前本地会话的 `access token`
2. 调云端 `server` 时带上 `Authorization`

### 6.2 本地鉴权接口

当前已落地接口：

#### `POST /api/v1/auth/session`

作用：

1. 设置或更新 `core` 当前会话

请求体：

```json
{
  "access_token": "<jwt>",
  "user_id": "user_xxx"
}
```

响应：

```json
{
  "status": "ok",
  "user_id": "user_xxx"
}
```

#### `DELETE /api/v1/auth/session`

作用：

1. 清空 `core` 当前会话

响应：

```json
{
  "status": "ok",
  "user_id": null
}
```

### 6.3 Core 调 Server 的要求

`core` 调用受保护 `server` 接口时必须带：

```http
Authorization: Bearer <access_token>
X-Request-ID: req_xxxxxxxxxxxx
```

### 6.4 Core 处理 401 的当前约束

当前最小实现：

1. 如果 `server` 返回 `401`
2. `core` 返回本地错误
3. 由 `client` 负责刷新并重新同步 token

当前不做：

1. `core` 内部持有 `refresh token`
2. `core` 自动静默刷新

## 7. Server 规范

### 7.1 Server 内部模型

当前内部用户文档主键字段为：

1. `user["_id"]`

当前对外用户响应字段为：

1. `user_profile()["id"]`

规则：

1. 存储层、鉴权层、业务逻辑层内部统一使用 `_id`
2. 对外返回 `JSON` 时统一映射为 `id`

### 7.2 当前受保护接口

至少包括：

1. `GET /api/v1/me`
2. `POST /v1/chat/completions`
3. 未来所有 `embedding / search / quota` 相关接口

### 7.3 Server 鉴权顺序

受保护接口统一按以下顺序处理：

1. 解析 `Authorization`
2. 校验 `Bearer` 格式
3. 解码 `JWT`
4. 校验 `exp / iss / aud`
5. 根据 `sid` 查服务端会话
6. 根据 `sub` 查用户文档
7. 检查用户状态是否 `active`
8. 再进入真实业务逻辑

### 7.4 Chat Proxy 规范

当前 `POST /v1/chat/completions` 已接入鉴权中间件。

它的职责是：

1. 复用当前用户和会话上下文
2. 生成 `OpenAI-compatible` 响应
3. 回传 `usage`
4. 回传 `entro_metadata`

当前 `entro_metadata` 至少包含：

```json
{
  "remaining_quota": null,
  "quota_status": "healthy",
  "user_id": "user_xxx"
}
```

注意：

1. `entro_metadata.user_id` 是内部主键值，但仍然通过对外契约字段名返回
2. 这里返回的是值，不是存储层字段名
3. 代码内部取值必须来自 `user["_id"]`

## 8. 错误语义

### 8.1 登录态缺失

场景：

1. `client` 未登录
2. `core` 尚未收到同步 token

推荐错误：

1. `401 AUTH_SESSION_REQUIRED`

### 8.2 Access Token 无效

场景：

1. token 过期
2. token 被篡改
3. 服务端会话已撤销

推荐错误：

1. `401 AUTH_TOKEN_INVALID`
2. `401 AUTH_TOKEN_EXPIRED`

### 8.3 用户不可用

场景：

1. 用户被禁用
2. 用户已不存在

推荐错误：

1. `403 USER_SUSPENDED`
2. `401 AUTH_TOKEN_INVALID`

### 8.4 Login Session 不可重复领取

规则：

1. `login_session` 只能成功领取一次
2. 第一次领取后，服务端会清空 `result`
3. 再次领取同一个 `login_session_id` 不应再拿到 token

前端必须避免重复消费同一个 `login_session_id`。

## 9. 当前工程约束

### 9.1 已知固定策略

当前实现刻意固定了这些策略：

1. `client` 负责刷新 token
2. `core` 不持有 `refresh token`
3. `server` 内部统一用 `_id`
4. `deep link` 不直接传 token
5. `login_session` 一次性消费

### 9.2 当前非目标

当前规范不覆盖：

1. 多租户团队权限模型
2. `RBAC`
3. 邮箱密码登录
4. 多因素认证
5. 生产环境安全加固细节
6. `refresh token rotation` 的更细策略

## 10. 给新工程师的接入清单

如果你在接入新的 `server` 受保护接口，按这个检查：

1. 是否复用了统一鉴权依赖
2. 内部是否只读 `_id`，而不是混用 `id`
3. 对外响应是否做了字段映射
4. 是否返回稳定错误码
5. 是否需要 `client` 或 `core` 在登录后额外同步状态

如果你在接入新的 `client` 登录相关逻辑，按这个检查：

1. 登录成功后是否同步给 `core`
2. token 刷新后是否再次同步给 `core`
3. 登出后是否通知 `core` 清空会话
4. 是否避免重复消费同一个 `login_session_id`

如果你在接入新的 `core -> server` 能力，按这个检查：

1. 是否自动带上 `Authorization: Bearer <access_token>`
2. `401` 是否会被前端感知并触发重新登录或刷新
3. 是否把云端错误映射成本地稳定错误

## 11. 当前代码落点

关键文件：

1. `server/app/auth_service.py`
   - `OAuth`、用户映射、`JWT` 签发
2. `server/app/auth_store.py`
   - 用户、会话、`refresh token`、`login_session`
3. `server/app/main.py`
   - 鉴权依赖、`/me`、`/v1/chat/completions`
4. `client/src/services/authClient.ts`
   - 登录、刷新、登出、领取 `login_session`
5. `client/src/store/useAuthStore.ts`
   - 前端登录态编排
6. `client/src/services/coreClient.ts`
   - `client -> core` 的 token sync 接口
7. `core/server.py`
   - 本地 auth session、`core -> server` chat 调用

## 12. 维护建议

后续如果扩展鉴权系统，优先顺序建议是：

1. 先保持这条链路稳定
2. 再接真实上游 `LLM provider`
3. 再补 `quota / rate limit`
4. 最后再扩展更多登录方式

不要在 `client`、`core`、`server` 三边各自长出一套独立鉴权逻辑。

正确方向始终是：

1. 登录入口在 `client`
2. 身份真相在 `server`
3. 执行凭证同步到 `core`
