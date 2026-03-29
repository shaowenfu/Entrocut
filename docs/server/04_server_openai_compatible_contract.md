# Server OpenAI-Compatible Contract

本文档定义当前重构阶段 `Core -> Server` 的最小云端通信契约。

用户登录、注册、用户管理、`JWT` 签发与 `OAuth` 流程，统一以 [Server Auth System Design](./03_server_auth_system_design.md) 为准。

当前已经落地的实现细节，尤其是：

1. `client -> core` 的 token sync
2. `server` 内部统一使用 `_id`、对外映射 `id`
3. `login_session` 一次性消费语义
4. `client / core / server` 的职责边界

统一以 [Auth Implementation Spec](./05_auth_implementation_spec.md) 为准。

换句话说：

1. 本文档定义 `Core -> Server` 的云端通信契约
2. `Auth Implementation Spec` 定义这条契约在当前代码里的具体身份链路和工程约束

阅读建议：

1. 想知道“请求和响应长什么样”，先看本文档
2. 想知道“token 从哪来、怎么同步、内部字段怎么命名”，看 `Auth Implementation Spec`

核心原则只有一条：

`Server API` 全面对齐 `OpenAI Chat Completions API`，不发明新的主数据格式。

这样做的直接收益是：

1. `Core` 可以直接复用 `openai-python`、`LangChain` 等成熟客户端
2. `Server` 可以在不改 `Core` 的前提下切换 `provider（模型供应商）`
3. `Client / Core / Server` 三端可以围绕稳定契约并行开发

## 1. 设计目标

当前 `Server contract` 只覆盖以下能力：

1. 健康检查与运行能力探测
2. 基于 EntroCut `access token` 的 `JWT auth（JWT 鉴权）`
3. `chat completions（对话生成）` 中转
4. `SSE（服务器发送事件）` 流式返回
5. `quota metadata（额度元数据）` 回传
6. 结构化错误语义

说明：

1. 本文档只覆盖开放式推理与 `OpenAI-compatible` 主链
2. `vectorize / retrieval / inspect` 这类专用工具能力不在本文档内定义
3. 它们应走独立 `REST tool contracts`

当前明确 `Non-goals（非目标）`：

1. 不保证完整覆盖所有 `OpenAI API` 参数
2. 不暴露 `provider` 私有字段
3. 不暴露内部数据库、计费账本、队列实现
4. 不在契约层泄露 `DashScope / OpenAI / Zhipu` 等真实路由细节
5. 不在本文档定义 `Core -> Client` 的本地事件流

## 2. 设计原则

1. 兼容优先：优先复用 `OpenAI-compatible（OpenAI 兼容）` 结构
2. 最小集合：只定义当前真实会使用的字段
3. 错误可枚举：所有失败必须能被 `Core` 稳定分支处理
4. 边界清晰：契约表达能力，不表达内部实现
5. 流式优先：`chat` 默认以 `SSE` 作为主交互模式

## 3. 顶层接口面

当前 `Server` 对 `Core` 暴露以下稳定接口：

1. `GET /health`
2. `GET /api/v1/runtime/capabilities`
3. `POST /v1/chat/completions`

后续可扩展但暂未纳入本文档的接口：

1. `POST /v1/embeddings`
2. `POST /api/v1/search`
3. `GET /api/v1/quota`
4. `POST /v1/assets/vectorize`
5. `POST /v1/assets/retrieval`
6. `POST /v1/tools/inspect`

## 4. 通用请求约定

### 4.1 Headers

所有需要鉴权的请求统一要求：

```http
Authorization: Bearer <jwt>
X-Request-ID: req_xxxxxxxxxxxx
Content-Type: application/json
```

可选头：

```http
X-Core-Version: 1.2.0
```

规则：

1. `Authorization` 用于用户身份识别与额度校验
2. `X-Request-ID` 用于跨 `Client / Core / Server` 链路追踪
3. `X-Core-Version` 仅用于兼容性观察，不参与鉴权

### 4.2 身份约定

`Core` 不直接持有真实 `provider API key`，只持有 EntroCut `server` 在登录成功后签发的 `access token`。

`Server` 负责：

1. 校验 `JWT signature（JWT 签名）`
2. 校验过期时间
3. 解析用户身份
4. 校验用户状态、会话状态、额度状态
5. 在内部注入真实 `provider credential（供应商凭证）`

说明：

1. 第三方 `Google/GitHub OAuth token` 不属于 `Core -> Server` 契约的一部分
2. `Core` 和 `client` 后续系统内通信只认 EntroCut 自己的 token

## 5. 通用错误 Envelope

所有非流式错误在建立 `SSE` 连接前返回统一 JSON：

```ts
interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    type: "auth_error" | "billing_error" | "rate_limit_error" | "provider_error" | "invalid_request_error" | "server_error";
    details?: Record<string, unknown>;
    request_id?: string;
  };
}
```

规则：

1. `code` 供 `Core` 做稳定分支判断
2. `message` 供日志与用户提示
3. `type` 供错误大类归并
4. `details` 只放必要上下文，不暴露内部栈
5. `request_id` 必须可用于链路排查

推荐错误码：

1. `AUTH_TOKEN_MISSING`
2. `AUTH_TOKEN_INVALID`
3. `AUTH_TOKEN_EXPIRED`
4. `QUOTA_EXCEEDED`
5. `RATE_LIMITED`
6. `MODEL_NOT_FOUND`
7. `UPSTREAM_TIMEOUT`
8. `UPSTREAM_UNAVAILABLE`
9. `INVALID_REQUEST`
10. `SERVER_INTERNAL_ERROR`
11. `USER_SUSPENDED`

## 6. Chat Completions Contract

### 6.1 Endpoint

```http
POST /v1/chat/completions
```

### 6.2 Request Schema

`Server` 应优先兼容以下最小字段：

```ts
interface ChatCompletionRequest {
  model: string;
  messages: Array<{
    role: "system" | "user" | "assistant" | "tool";
    content: string;
    name?: string;
  }>;
  stream?: boolean;
  temperature?: number;
  max_tokens?: number;
}
```

请求示例：

```json
{
  "model": "entro-reasoning-v1",
  "messages": [
    {
      "role": "system",
      "content": "You are the Agent brain of a video editor. Context: {\"assets\": []}"
    },
    {
      "role": "user",
      "content": "帮我剪一个高燃片段"
    }
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 2000
}
```

规则：

1. `model` 必须是 `virtual model name（虚拟模型名）`，例如 `entro-reasoning-v1`
2. `Core` 不应传真实 `provider model name（供应商模型名）`
3. `stream` 当前推荐始终为 `true`
4. 未声明支持的参数可忽略或返回 `INVALID_REQUEST`

### 6.3 虚拟模型路由

`model` 字段代表产品级能力，而不是底层供应商实现。

例如：

1. `entro-reasoning-v1`
2. `entro-fast-chat-v1`
3. `entro-vision-index-v1`

`Server` 内部负责将其映射到真实模型，例如：

1. `qwen-max`
2. `gpt-4.1`
3. `glm-4`

这层映射不属于对外契约。

## 7. Streaming Contract

### 7.1 响应类型

当 `stream=true` 时，`Server` 必须返回：

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

### 7.2 中间 Chunk

中间数据块应尽量保持 `OpenAI-compatible`：

```text
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1709860000,"model":"entro-reasoning-v1","choices":[{"index":0,"delta":{"role":"assistant","content":"好的"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1709860000,"model":"entro-reasoning-v1","choices":[{"index":0,"delta":{"content":"，我"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1709860000,"model":"entro-reasoning-v1","choices":[{"index":0,"delta":{"content":"开始"},"finish_reason":null}]}
```

规则：

1. `Core` 只需要持续提取 `choices[0].delta.content`
2. `Server` 不应在中间块注入产品私有结构
3. 除非必要，不改写上游块内容

### 7.3 Final Chunk

最终结束块允许在标准结构上追加产品扩展字段：

```text
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1709860000,"model":"entro-reasoning-v1","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":520,"completion_tokens":130,"total_tokens":650},"entro_metadata":{"remaining_quota":4350,"quota_status":"healthy"}}

data: [DONE]
```

字段约定：

```ts
interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

interface EntroMetadata {
  remaining_quota: number;
  quota_status: "healthy" | "warning" | "exhausted";
}
```

规则：

1. `usage` 是标准字段，必须可用
2. 产品扩展统一挂在 `entro_metadata`
3. `entro_metadata` 只出现在最终块，不出现在中间块
4. 最终必须以 `data: [DONE]` 结束

## 8. Non-Streaming Contract

当 `stream=false` 时，`Server` 应返回标准 JSON 响应，而不是 `SSE`。

最小兼容结构：

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1709860000,
  "model": "entro-reasoning-v1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "好的，我开始帮你规划高燃片段。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 520,
    "completion_tokens": 130,
    "total_tokens": 650
  },
  "entro_metadata": {
    "remaining_quota": 4350,
    "quota_status": "healthy"
  }
}
```

当前实现建议优先保障 `stream=true`，`stream=false` 可作为兼容面保留。

## 9. 异常与拦截契约

所有鉴权、额度、限流错误，必须在建立流之前直接返回 `HTTP error + JSON`。

### 9.1 401 Unauthorized

适用场景：

1. 缺少 `Authorization`
2. `JWT` 无效
3. `JWT` 已过期
4. 会话已撤销

示例：

```json
{
  "error": {
    "code": "AUTH_TOKEN_INVALID",
    "message": "The provided JWT token is expired or invalid.",
    "type": "auth_error"
  }
}
```

### 9.2 402 Payment Required

适用场景：

1. 用户额度耗尽

示例：

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "Your API quota has been exhausted. Please upgrade your plan.",
    "type": "billing_error"
  }
}
```

### 9.3 429 Too Many Requests

适用场景：

1. 用户触发 `RPM / TPM` 限流

示例：

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Please retry later.",
    "type": "rate_limit_error"
  }
}
```

### 9.4 5xx Upstream / Server Error

适用场景：

1. 上游模型超时
2. 上游模型不可用
3. `Server` 内部异常

示例：

```json
{
  "error": {
    "code": "UPSTREAM_UNAVAILABLE",
    "message": "The model provider is temporarily unavailable.",
    "type": "provider_error"
  }
}
```

### 9.5 403 Forbidden

适用场景：

1. 用户状态为 `suspended`
2. 当前身份无权访问目标资源

示例：

```json
{
  "error": {
    "code": "USER_SUSPENDED",
    "message": "The current user is suspended.",
    "type": "auth_error"
  }
}
```

## 10. Core 侧最小解析要求

`Core` 只需实现以下稳定逻辑：

1. 为每次请求附带 `Authorization` 与 `X-Request-ID`
2. 发送 `OpenAI-compatible request body`
3. 逐块解析 `choices[0].delta.content`
4. 在最终块读取 `usage` 与 `entro_metadata`
5. 在收到 `401 / 402 / 403 / 429` 时中断 `Agent loop（Agent 循环）`

这意味着 `Core` 不需要理解真实 `provider` 协议。

## 11. Runtime Contract

### 11.1 `GET /health`

用途：

1. 服务健康探测
2. 本地开发联调

最小返回建议：

```json
{
  "status": "ok",
  "service": "server",
  "version": "0.6.0-skeleton",
  "phase": "clean_room_rewrite",
  "mode": "contract_first",
  "timestamp": "2026-03-08T10:00:00Z"
}
```

### 11.2 `GET /api/v1/runtime/capabilities`

用途：

1. 告诉 `Core / Client` 当前 `Server` 已启用哪些能力
2. 作为开发阶段兼容探针

最小返回建议：

```json
{
  "service": "server",
  "version": "0.6.0",
  "capabilities": {
    "planner_chat": { "available": true },
    "multimodal_embedding": { "available": true, "model": "qwen3-vl-embedding" },
    "vector_retrieval": { "available": true, "provider": "dashvector" },
    "inspect_image": { "available": true, "provider": "gemini", "mode": "ordered_keyframes" },
    "inspect_video": { "available": false, "reason": "not_enabled_in_phase_1" }
  }
}
```

## 12. 实现建议

推荐按以下顺序落地：

1. 先实现 `JWT middleware（JWT 中间件）`
2. 再实现 `POST /v1/chat/completions`
3. 再实现 `SSE proxy（SSE 中转）`
4. 最后接入 `quota / rate limit（额度 / 限流）`

原因：

1. 这样能最快打通 `Core -> Server -> Provider` 最短闭环
2. `embedding / search` 后续可以直接复用同一套鉴权、错误和计费框架

## 13. 一句话结论

`Server contract` 的最佳实践不是“重新设计一套协议”，而是“尽量伪装成标准 OpenAI 端点，只在最终块和错误语义上加最小产品扩展”。
