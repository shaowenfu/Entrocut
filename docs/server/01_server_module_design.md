# Server 端三大模块设计方案及原理：

> `2026-03-31` 注：本文档的业务分层判断仍然成立，但当前代码目录已经不再是早期扁平 `app/*.py` 结构，而是落位为 `bootstrap / api / core / repositories / schemas / services / shared` 七层结构。阅读代码时，请优先以当前目录现实为准。

一、 鉴权中心 (Authentication)
核心原理：无状态校验 (Stateless Verification)

既然 Core 在本地，Server 在云端，它们之间必须通过一种安全且轻量的方式“验明正身”。业内绝对的最佳实践是 JWT (JSON Web Token)。

信任三角流转：

登录 (Client -> Server)：用户在 React 界面输入账号密码（或 OAuth 授权），Server 校验通过后，签发一个签名的 JWT（有效期例如 7 天）。

下发 (Client -> Core)：Client 拿到 JWT 后，通过本地接口（如 localhost:8000/set_token）将 JWT 喂给本地 Core 进程。

请求 (Core -> Server)：Core 每次需要大模型思考时，在 HTTP Header 中带上 Authorization: Bearer <JWT> 发给 Server。

Server 端的鉴权拦截器 (Auth Middleware)：

Server 收到请求后，不需要查数据库，只需用自己的密钥（Secret）校验 JWT 的签名是否合法、是否过期。

原理优势：极大地降低了数据库的并发查询压力（这被称为无状态鉴权）。

二、 用户与额度管理 (User & Quota Management)
核心原理：集中式账本与令牌桶 (Centralized Ledger & Token Bucket)

大模型的调用成本极高，Server 必须像银行一样精确管理每个用户的“余额”。

数据库设计 (mongoDB atlas云服务)：

限流防刷机制 (Rate Limiting - 极度重要)：

频次限制 (RPM/TPM)：利用 Redis 实现令牌桶算法。限制每个用户每分钟最多请求 10 次，或者每分钟最多生成 5000 个 Token。

原理优势：防止恶意用户通过抓包你的 Core，写脚本疯狂调用你的 Server 接口，导致你直接破产。

三、 模型中转站 (AI Model Proxy & Gateway)
核心原理：外观模式与流式透传 (Facade Pattern & Streaming Pipe)

这是 Server 最核心的业务。它必须表现得像一个标准的 AI 厂商，对内屏蔽所有复杂的云端对接逻辑。

统一的 API 契约 (OpenAI 兼容 + 专用工具网关)：

无论背后用的是阿里云 DashScope、OpenAI 还是智谱，`planner` 类推理请求都应尽量暴露为标准的 `POST /v1/chat/completions`。  
但像 `vectorize / retrieval / inspect` 这类专用工具能力，不应强行塞进 `OpenAI-compatible` 对话接口，而应通过专用 `REST tool endpoints` 暴露。

原理优势：

1. `Core` 端的通用 Agent 推理逻辑仍可直接复用标准库（如官方 `openai-python` 或 `LangChain`）
2. 专用工具调用保留结构化输入输出、错误语义与能力探针
3. 避免把视觉判定、向量检索等专用能力和开放式对话耦死

凭证注入与流式透传 (The Proxy Flow)：

拦截与注入：Server 拦截到 Core 的请求后，剥离用户的 JWT，注入你存在 Server 环境变量中的真实 API Key。

流式转发 (SSE)：调用外部大模型时，开启 stream=True。Server 接收到外部大模型吐出的每一个 Token，立即通过 Server-Sent Events (SSE) 协议，原封不动地 Pipe（管道式）推回给 Core。

异步计算消费：在流式传输结束后，Server 统计本次总共消耗了多少 Token，并异步丢给消息队列（或直接写库），扣除用户余额。

架构师的总结：Server 端的防线
在这个架构中，你的 Server 其实就是一个 BFF (Backend for Frontend/Core) 加上一个 API Gateway。

它不存视频，所以不需要庞大的对象存储（OSS）和高昂的带宽。

它不做剪辑决策，所以不需要维护复杂的工程状态和长时间的上下文内存。

它当前主要做四件事：“证明你是谁”、“看你还有没有钱”、“帮你安全地把话带给大模型”、“把向量检索与图像级 inspect 这类专用云端能力稳定中转给 Core”。

这种极简的 Server 架构非常利于快速上线，并且日后极易横向扩展（只需要多加几台机器跑 FastAPI 即可）。

## 当前代码目录映射

为了让“鉴权中心 / 用户与额度管理 / 模型中转站”这三大模块真正能在代码里被看清，当前 `server/app` 已经按下面的方式落位：

1. `bootstrap/`
   - `FastAPI app` 装配、依赖单例、健康探针、异常处理、中间件
2. `api/routes/`
   - `auth / user / chat / assets / inspect / runtime / health`
3. `core/`
   - `config / errors / observability / runtime_guard`
4. `repositories/`
   - `mongo_repository / login_session_repository / auth_store`
5. `schemas/`
   - `auth / user / runtime / assets / inspect`
6. `services/auth/`
   - `oauth / tokens / users`
7. `services/gateway/`
   - `provider_routing / chat_proxy / streaming / billing`
8. `services/vector.py`
9. `services/inspect.py`
10. `services/quota.py`

也就是说，本文档里的三大业务模块并没有变化，只是现在已经能和真实目录形成稳定映射：

1. 鉴权中心 -> `api/routes/auth.py` + `services/auth/` + `repositories/`
2. 用户与额度管理 -> `services/quota.py` + `repositories/mongo_repository.py`
3. 模型中转站 -> `api/routes/chat.py` + `services/gateway/`

# server 与 core 的通信契约

### 核心准则：对开放式推理尽量向 OpenAI Chat Completions API 对齐；对专用工具能力提供独立网关

### 一、 请求契约：Core -> Server (模型请求规范)

请求体应该保持极度干净，身份验证通过 HTTP Header 传递，业务数据通过 JSON 负载 (Payload) 传递。

**1. HTTP Headers (头部信息)**

**2. JSON Body (请求负载)**

---

### 二、 响应契约：Server -> Core (流式 Token 返回规范)

既然是流式传输，Server 必须使用 **服务器发送事件 (Server-Sent Events, SSE)** 协议。数据是一块一块（Chunk）吐给 Core 的。

### 1. 过程中的数据块 (Intermediate Chunks)

Server 一边从阿里云接收 Token，一边原封不动地 Pipe（透传）给 Core。

- **解析逻辑**：Core 端的 Agent 只需要不断提取 `choices[0].delta.content`，并在本地拼接字符串，同时可以通过 WebSocket 实时推给 Client 渲染在 UI 上。

### 2. 结束块与额度注入 (The Final Chunk & Quota Injection)

这是 SaaS 产品最核心的巧思。在生成结束时，Server 截获最后一个 Chunk，并在其中**注入 Token 消耗量和用户的剩余额度**。

- **`usage` 字段**：标准的 OpenAI 统计字段，告诉 Core 这次消耗了多少。
- **`entro_metadata` 字段**：我们自定义的扩展字段。Core 拿到这个字段后，可以通知 Client 端的 Zustand Store 更新 UI（比如当 `remaining_quota` 低于 1000 时，在工作台右上角亮起黄灯警告）。

---

### 三、 异常与拦截契约 (Error Handling)

当用户的额度用尽，或者 JWT 过期时，Server 需要在建立 SSE 连接**之前**就果断拦截，并返回标准的 HTTP 状态码和 JSON 错误信息。

**额度耗尽 (402 Payment Required 或 403 Forbidden)**

**Token 失效 (401 Unauthorized)**

- **Core 的应对逻辑**：Core 的请求库捕获到 401 或 402 后，立刻中断 Agent 的思考循环 (Agent Loop)，并通过 WebSocket 发送 `ERROR_EVENT` 给 Client，Client 随即弹出“请重新登录”或“请充值”的系统弹窗。

---

### 架构师的设计总结

1. **开放式推理尽量“伪装”成标准大模型**：让你的 `planner` 请求尽量走标准 `OpenAI` 端点，这极大地降低了 `Core` 端的开发成本。
2. **解耦路由策略 (Routing Strategies)**：通过定义 `entro-reasoning-v1` 这种虚拟模型名，Server 可以在后端随时将流量从阿里云切换到其他更便宜或更快的模型，而不用发布 Core 的更新。
3. **专用工具独立暴露**：像 `vectorize / retrieval / inspect` 这类工具能力必须保留独立契约，不能让它们淹没在通用 `chat` 接口里。
4. **计费闭环**：通过最后一个 Chunk 的 `usage` 实现了精确的成本追踪；专用工具则通过各自的结构化响应和日志打点计费。

按照这个契约，Server 端的工程师和 Core 端的工程师现在就可以完全并行开发了。
