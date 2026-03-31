# Server 目录重构任务

日期：`2026-03-31`

## 目标

在 **不改变任何业务逻辑** 的前提下，对 `server/` 进行一次完整的目录体系优化，使其更贴近 `FastAPI` 主流最佳实践，并显著降低以下问题：

1. `server/app/main.py` 过重，混合了 `bootstrap（启动装配）`、`middleware（中间件）`、`exception handling（异常处理）`、`dependency（依赖）`、多组 `route（路由）` 与 `chat gateway（聊天网关）` 逻辑。
2. `server/app/auth_store.py` 同时承担 `Mongo repository（Mongo 仓储）`、`Redis login session（Redis 登录会话）`、`in-memory fallback（内存回退）`、`quota ledger（额度账本）` 等多重职责。
3. `server/app/models.py` 把所有 `schema（模式）` 堆在同一个文件里，已经影响阅读与维护。

## 重构原则

1. 只做文件搬迁、模块拆分、`import` 调整与必要的兼容入口瘦身。
2. 不修改任何外部 HTTP 接口。
3. 不修改任何 `schema field（模式字段）`。
4. 不修改任何错误码与错误语义。
5. 不引入新的 `DI container（依赖注入容器）`、`service locator（服务定位器）` 或额外框架。
6. 目录主轴采用 `technical-layer（技术分层）`，但对复杂区域保留少量子目录聚合，避免过度碎片化。

## 目标结构

```text
server/
├── main.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── bootstrap/
│   │   ├── app.py
│   │   ├── dependencies.py
│   │   ├── exception_handlers.py
│   │   ├── lifespan.py
│   │   └── middleware.py
│   ├── api/
│   │   ├── router.py
│   │   └── routes/
│   │       ├── assets.py
│   │       ├── auth.py
│   │       ├── chat.py
│   │       ├── health.py
│   │       ├── inspect.py
│   │       ├── runtime.py
│   │       └── users.py
│   ├── core/
│   │   ├── config.py
│   │   ├── errors.py
│   │   ├── observability.py
│   │   └── runtime_guard.py
│   ├── repositories/
│   │   ├── auth_store.py
│   │   ├── login_session_repository.py
│   │   └── mongo_repository.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── assets.py
│   │   ├── auth.py
│   │   ├── common.py
│   │   ├── inspect.py
│   │   ├── runtime.py
│   │   └── user.py
│   ├── services/
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── oauth.py
│   │   │   ├── tokens.py
│   │   │   ├── users.py
│   │   │   └── utils.py
│   │   ├── gateway/
│   │   │   ├── billing.py
│   │   │   ├── chat_proxy.py
│   │   │   ├── provider_routing.py
│   │   │   └── streaming.py
│   │   ├── inspect.py
│   │   ├── quota.py
│   │   └── vector.py
│   └── shared/
│       └── time.py
└── tests/
```

## 实施边界

### 1. 保持稳定入口

以下入口保持稳定：

1. `server/main.py`
2. `server/app/main.py`
3. `server/app/__init__.py`

其中 `server/app/main.py` 退化为薄入口，只负责重新导出 `app` 与少量测试所需全局对象。

### 2. 大文件拆分策略

#### `app/main.py`

按职责拆为：

1. `bootstrap/`：应用装配、生命周期、异常处理、中间件、依赖
2. `api/routes/`：所有 HTTP 路由
3. `services/gateway/`：`chat proxy` 的 provider routing、upstream call、streaming、billing

#### `app/auth_store.py`

按职责拆为：

1. `repositories/mongo_repository.py`
2. `repositories/login_session_repository.py`
3. `repositories/auth_store.py`

其中 `AuthStore` 保留为轻量聚合入口，避免本次重构改动面过大。

#### `app/models.py`

按接口域拆为：

1. `schemas/runtime.py`
2. `schemas/auth.py`
3. `schemas/user.py`
4. `schemas/assets.py`
5. `schemas/inspect.py`
6. `schemas/common.py`

## 非目标

本次明确不做：

1. 不重写任何服务内部算法。
2. 不引入新的 repository interface（仓储接口）抽象层。
3. 不调整任何鉴权、计费、向量、检索、`inspect` 业务逻辑。
4. 不修改运行配置语义。
5. 不做额外产品化增强。

## 验收标准

1. 现有 `server/tests` 全部通过。
2. `uvicorn server.main:app` 入口不变。
3. 目录结构从单层扁平转为清晰的 `technical-layer` 结构。
4. 原始重文件被拆散，`main.py / auth_store.py / models.py` 明显瘦身。
5. 没有新增业务行为变化。
