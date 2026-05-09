# Registry-driven Model Routing（注册表驱动模型路由）全链路改造方案

日期：`2026-05-05`

## 1. 背景

当前 `model routing（模型路由）` 的主要问题不是单个页面或单个接口缺失，而是 `client（客户端）`、`core（本地引擎）`、`server（服务端）` 对模型能力的表达不一致：

1. `Platform（平台托管）` 模式仍暴露 `entro-reasoning-v1` 这类虚拟模型，但用户和开发者真正需要看到的是厂商真实 `model id（模型标识）`。
2. `server（服务端）` 仍通过全局 `llm_proxy_mode` 区分 `mock / google_gemini / upstream`，导致 provider（供应商）路由和请求逻辑混在一起。
3. `mock（模拟）` 模式已经不适合作为运行时 provider（供应商）；测试可以继续使用 test double（测试替身），但不应出现在 production runtime（生产运行时）契约里。
4. `BYOK（Bring Your Own Key，自带密钥）` 模式把 `endpoint（接口地址）`、`chat path（聊天路径）`、`headers（请求头）` 暴露给用户，增加误配风险，也把开发者应该维护的 integration detail（接入细节）推给了用户。

本方案采用 `Provider Registry（供应商注册表）` + `Provider Adapter（供应商适配器）` 的架构，把“开发者维护接入方式”和“用户选择 provider/model/key（供应商/模型/密钥）”明确分离。

## 2. 目标

1. `Platform（平台托管）` 模式直接使用真实 `model id（模型标识）`，不再使用平台虚拟模型。
2. 删除 server runtime（服务端运行时）中的 `mock（模拟）` 模式。
3. 删除原有 `mock / google_gemini / upstream` 全局模式分支，改为按请求中的 `provider` + `model` 查 `Provider Registry（供应商注册表）`。
4. 将 provider 请求逻辑拆成独立 `Provider Adapter（供应商适配器）`：
   - 支持 `OpenAI-compatible（兼容 OpenAI 接口）` 的 provider 统一走一个 adapter，例如 `DeepSeek`。
   - `Gemini` 等非统一协议 provider 使用专门 adapter。
5. `BYOK（自带密钥）` 模式只让用户选择 `provider（供应商）`、`model（模型）` 并填写 `API key（接口密钥）`，不再填写 endpoint。
6. 用户本地保存的 BYOK provider 配置持久化到本地；密钥走 encrypted storage（加密存储），可随时保存、更新、删除。
7. `Model panel（模型面板）` 改为先选 `provider（供应商）`，再选 `model（模型）`，并保留 `custom model id（自定义模型标识）`。

## 3. 非目标

1. 本次不实现新的 billing model（计费模型），仍沿用 `Platform（平台托管）` 扣 `remaining_quota（剩余额度）`，`BYOK（自带密钥）` 不扣平台 quota（额度）。
2. 本次不实现多个 BYOK account profile（多账号配置档），只按 provider 保存一份当前 key。
3. 本次不把用户自定义 endpoint 作为高级功能保留。endpoint 由开发者维护。
4. 本次不把 `mock（模拟）` 暴露为任何 runtime provider（运行时供应商）。

## 4. 目标架构

### 4.1 统一概念

全链路统一使用以下概念：

```text
routing_mode: Platform | BYOK
provider_id: deepseek | google_gemini
model_id: deepseek-v4-flash | deepseek-v4-pro | gemini-2.5-flash | ...
custom_model_id: string | null
```

`effective_model_id（实际模型标识）` 的计算规则：

```text
custom_model_id 非空 -> 使用 custom_model_id
否则 -> 使用 model_id
```

### 4.2 Platform（平台托管）架构

```text
client model panel
  -> provider_id + model_id
  -> core chat request
  -> server /v1/chat/completions
  -> server Provider Registry
  -> provider-specific Adapter
  -> cloud provider API
  -> normalized OpenAI-compatible response
  -> quota update
  -> core planner decision
  -> WebSocket event
  -> client chat UI
```

`server（服务端）` 的 registry 决定平台支持哪些 provider/model，并从 server env（环境变量）读取平台密钥。

### 4.3 BYOK（自带密钥）架构

```text
client model panel
  -> provider_id + model_id + encrypted API key
  -> core chat request
  -> core Local Provider Registry
  -> local provider adapter or OpenAI-compatible caller
  -> cloud provider API
  -> core planner decision
  -> WebSocket event
  -> client chat UI
```

`BYOK（自带密钥）` 初期只提供 `DeepSeek` 一种本地接入方案。用户只需要填入 DeepSeek API key，并选择 DeepSeek model。

## 5. API Contract（接口契约）

### 5.1 client -> core chat request

当前 `core` 的 chat request 需要从只传 `model` 扩展为：

```json
{
  "prompt": "用户输入",
  "target": {
    "scene_id": null,
    "shot_id": null
  },
  "routing": {
    "mode": "Platform",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "custom_model": null
  }
}
```

兼容策略：

1. 短期可保留旧 `model` 字段作为 fallback（兜底）。
2. 新 UI 只发送 `routing`。
3. core 内部统一转换为 `ChatRoutingConfig（聊天路由配置）`。

### 5.2 core -> server platform request

`Platform（平台托管）` 模式下，core 请求 server 时 payload 应包含：

```json
{
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "stream": false,
  "temperature": 0.1,
  "max_tokens": 6000,
  "messages": []
}
```

server 不再根据全局 `llm_proxy_mode` 推断 provider，而是根据 `provider` 字段路由。

### 5.3 runtime models response

`GET /api/v1/runtime/models` 返回 provider 分组，而不是单个虚拟模型：

```json
{
  "default_provider": "deepseek",
  "default_model": "deepseek-v4-flash",
  "providers": [
    {
      "id": "deepseek",
      "label": "DeepSeek",
      "available": true,
      "models": [
        {
          "id": "deepseek-v4-flash",
          "label": "DeepSeek Chat",
          "available": true,
          "supports_custom_model": true
        },
        {
          "id": "deepseek-v4-pro",
          "label": "DeepSeek Reasoner",
          "available": true,
          "supports_custom_model": true
        }
      ]
    },
    {
      "id": "google_gemini",
      "label": "Google Gemini",
      "available": true,
      "models": [
        {
          "id": "gemini-2.5-flash",
          "label": "Gemini 2.5 Flash",
          "available": true,
          "supports_custom_model": true
        }
      ]
    }
  ],
  "warnings": []
}
```

`server/app/api/routes/runtime.py:42` 附近的 `default_model` 要改为真实 model id，不再返回 `entro-reasoning-v1`。

## 6. Server（服务端）改造方案

### 6.1 模块拆分

建议新增：

```text
server/app/services/models/
  schemas.py
  registry.py
  gateway.py
  adapters/
    base.py
    openai_compatible.py
    gemini.py
```

职责：

1. `schemas.py`：定义 `ProviderDefinition（供应商定义）`、`ModelDefinition（模型定义）`、`ChatRequestContext（聊天请求上下文）`、`NormalizedChatResponse（归一化聊天响应）`。
2. `registry.py`：维护平台 provider/model 列表，读取 settings/env 判断是否 available。
3. `gateway.py`：根据 request provider 查 registry，再调用对应 adapter。
4. `adapters/openai_compatible.py`：统一处理 DeepSeek 这类 OpenAI-compatible provider。
5. `adapters/gemini.py`：处理 Gemini 专有请求方案和 response normalize。

### 6.2 删除旧模式

需要删除或废弃：

1. `llm_proxy_mode`
2. `llm_default_model=entro-reasoning-v1`
3. `llm_upstream_*`
4. `mock_chat_content`
5. `effective_llm_proxy_mode`
6. `resolve_chat_provider`
7. `resolve_upstream_model`

如果为了迁移风险需要分阶段，可以先保留字段但不再被 runtime path（运行时路径）使用，并在文档中标记 deprecated（废弃）。

### 6.3 Provider Registry（供应商注册表）

初期平台 provider：

```text
deepseek
  adapter: openai_compatible
  base_url: https://api.deepseek.com
  chat_path: /chat/completions
  api_key_env: DEEPSEEK_API_KEY
  models:
    - deepseek-v4-flash
    - deepseek-v4-pro

google_gemini
  adapter: gemini
  api_key_env: GOOGLE_API_KEY
  models:
    - gemini-2.5-flash
    - gemini-2.5-pro
```

`custom model id（自定义模型标识）` 只覆盖 model，不覆盖 endpoint/provider。

### 6.4 Quota（额度）与 usage（用量）

`Platform（平台托管）` 保持现有语义：

1. 请求前 `quota_service.assert_can_chat()`。
2. 请求后从 provider response 读取 usage。
3. 如果 provider 不返回 usage，使用 server fallback estimator（兜底估算器）。
4. 调用 `quota_service.record_chat_usage()`。
5. MongoDB 更新 `users.remaining_quota / quota_status`，并插入 `quota_ledgers`。

注意：`Provider Adapter（供应商适配器）` 只负责返回 normalized usage，不直接更新 quota。

## 7. Core（本地引擎）改造方案

### 7.1 Chat routing model

core 增加统一结构：

```py
class ChatRoutingConfig:
    mode: Literal["Platform", "BYOK"]
    provider: str
    model: str
    custom_model: str | None
```

core route 负责把 client request 转换成该结构。

### 7.2 Platform path（平台路径）

core 在 Platform 模式下：

1. 要求已同步 server access token。
2. 调 server `/v1/chat/completions`。
3. payload 带 `provider` 和真实 `model`。
4. 不再使用 `SERVER_CHAT_MODEL=entro-reasoning-v1`。

### 7.3 BYOK path（自带密钥路径）

core 增加 local provider registry（本地供应商注册表）。初期：

```text
deepseek
  adapter: openai_compatible
  base_url: https://api.deepseek.com
  chat_path: /chat/completions
  models:
    - deepseek-v4-flash
    - deepseek-v4-pro
```

core 不接受用户传入 endpoint。client 只传 provider/model/key。

### 7.4 Response parsing（响应解析）

core 仍然要求最终 assistant message content 包含 `PlannerDecisionModel（规划器决策模型）` JSON。

删除 server mock 后，测试应改为在 core tests 中 patch adapter response（替换适配器响应），而不是依赖 runtime mock provider。

## 8. Client（客户端）改造方案

### 8.1 Model panel（模型面板）

UI 改为：

```text
Mode
  [ Platform | BYOK ]

Provider
  [ DeepSeek | Google Gemini ]       // Platform
  [ DeepSeek ]                       // BYOK 初期

Model
  [ deepseek-v4-flash | deepseek-v4-pro | Custom... ]

Custom model id
  [ input ]                          // 选择 Custom 后展示

API Key
  [ password input ]                 // 仅 BYOK
  [ Save / Update ] [ Delete ]
```

### 8.2 Client state（客户端状态）

建议替换当前 `modelPrefs`：

```ts
interface ModelPreferences {
  routingMode: "Platform" | "BYOK";
  platformProvider: string;
  platformModel: string;
  platformCustomModel: string;
  byokProvider: string;
  byokModel: string;
  byokCustomModel: string;
  byokKeySavedByProvider: Record<string, boolean>;
}
```

`API key（接口密钥）` 不进 `localStorage（本地存储）`，只进 encrypted storage（加密存储）。

### 8.3 Credential storage（凭据存储）

key 命名：

```text
entrocut.byok.deepseek.api_key
```

操作：

1. `saveByokProviderKey(provider, key)`
2. `loadByokProviderKey(provider)`
3. `deleteByokProviderKey(provider)`
4. `hasByokProviderKey(provider)`

UI 中展示 `Saved（已保存）/ Missing（未保存）/ Updating（更新中）/ Error（错误）` 状态。

### 8.4 迁移旧配置

旧字段：

1. `byokBaseUrl`
2. `byokChatPath`
3. `byokHeadersJson`
4. 旧 `entrocut.byok.api_key`

处理策略：

1. 不自动把旧 endpoint 转成新 provider，避免误绑到 DeepSeek。
2. 旧 key 不自动启用。
3. UI 可显示一次性提示：`BYOK provider settings changed. Please save your DeepSeek API key again.`
4. 提供删除旧 key 的 cleanup（清理）逻辑。

## 9. 并行任务组织

### Engineer A：Server Registry & Adapter（服务端注册表与适配器）

范围：

1. 新增 `server/app/services/models/*`。
2. 实现 platform provider registry。
3. 实现 `OpenAI-compatible Adapter（兼容 OpenAI 适配器）`。
4. 实现 `Gemini Adapter（Gemini 适配器）`。
5. 删除 runtime mock path（运行时模拟路径）。
6. 改造 `/v1/chat/completions` 使用 provider registry。
7. 改造 `/api/v1/runtime/models` 返回 provider 分组和真实 model id。

依赖：

1. 与 Engineer B 对齐 core -> server request schema。
2. 与 Engineer C 对齐 runtime models response schema。

验收：

1. 没有 `mock` runtime provider。
2. `runtime/models` 不返回 `entro-reasoning-v1`。
3. DeepSeek 走 OpenAI-compatible adapter。
4. Gemini 走独立 adapter。
5. Platform 请求后仍写 MongoDB quota ledger。

### Engineer B：Core Routing（本地引擎路由）

范围：

1. 扩展 core chat request schema。
2. 引入 `ChatRoutingConfig（聊天路由配置）`。
3. Platform path 发送 `provider/model` 到 server。
4. BYOK path 使用 local provider registry，不再接受 endpoint/header。
5. BYOK 初期只支持 DeepSeek。
6. 清理 `SERVER_CHAT_MODEL=entro-reasoning-v1` 的 planner 默认依赖。

依赖：

1. 需要 Engineer A 给出 server request contract。
2. 需要 Engineer C 给出 client request contract。

验收：

1. Platform 模式缺登录态仍返回明确 auth error。
2. BYOK 模式缺 key 返回明确 `BYOK_KEY_REQUIRED`。
3. BYOK 不能传任意 endpoint。
4. core 能解析真实 provider 返回的 planner JSON。

### Engineer C：Client Model Panel & Store（客户端模型面板与状态）

范围：

1. 重构 `WorkspacePage` model panel。
2. 重构 `useAuthStore.modelPrefs`。
3. 支持 provider -> model 两级选择。
4. 支持 custom model id。
5. 接入 provider-scoped encrypted key storage。
6. 实现 BYOK key 保存、更新、删除。
7. 更新 `sendChat` 请求结构。

依赖：

1. 需要 Engineer A 的 `runtime/models` response schema。
2. 需要 Engineer B 的 core chat request schema。

验收：

1. Platform 下只展示 DeepSeek / Google Gemini。
2. BYOK 下只展示 DeepSeek。
3. 用户看不到 endpoint/chat path/headers。
4. API key 不进入 `localStorage（本地存储）`。
5. 删除 key 后无法继续 BYOK 请求，且 UI 明确提示。

### Engineer D：Tests & Migration（测试与迁移）

范围：

1. 更新 server provider registry tests。
2. 更新 core chat routing tests。
3. 更新 client model preference tests。
4. 添加旧 BYOK config migration tests。
5. 添加 quota regression tests。
6. 更新开发文档与 `.env.example`。

依赖：

1. 等 A/B/C 的最小 contract 合并后开始集成测试。

验收：

1. 单元测试覆盖 provider/model resolution。
2. 集成测试覆盖 Platform DeepSeek path。
3. BYOK key 不落 localStorage。
4. 旧 mock runtime 不再被测试依赖。

## 10. 推荐实施顺序

### Phase 1：Contract first（先定契约）

1. 定义 shared schema（共享契约）：
   - runtime models response。
   - client -> core chat routing。
   - core -> server chat provider/model fields。
2. 更新文档和 tests fixture（测试夹具）。

### Phase 2：Server provider registry（服务端供应商注册表）

1. 新增 registry/adapters/gateway。
2. 改 `/api/v1/runtime/models`。
3. 改 `/v1/chat/completions`。
4. 移除 mock runtime。

### Phase 3：Core routing（本地引擎路由）

1. 扩展 chat schema。
2. 改 Platform request。
3. 改 BYOK request。
4. 删除 endpoint passthrough（接口透传）。

### Phase 4：Client UI and credentials（客户端 UI 与凭据）

1. 重构 model panel。
2. 重构 preferences。
3. 接入 encrypted key storage。
4. 完成旧配置迁移。

### Phase 5：Integration and cleanup（集成与清理）

1. 跑端到端手动测试。
2. 删除废弃 config 和 dead code（无用代码）。
3. 更新 docs。

## 11. 测试清单

### Server tests（服务端测试）

1. `runtime/models` 返回真实 provider/model。
2. 未配置 `DEEPSEEK_API_KEY` 时 DeepSeek provider `available=false`。
3. 未配置 `GOOGLE_API_KEY` 时 Gemini provider `available=false`。
4. Platform DeepSeek 请求调用 OpenAI-compatible adapter。
5. Platform Gemini 请求调用 Gemini adapter。
6. provider 不存在返回可枚举错误。
7. model 不存在且未显式 custom 返回可枚举错误。
8. usage 正常扣减 MongoDB `remaining_quota`。

### Core tests（本地引擎测试）

1. Platform chat payload 带 provider/model。
2. BYOK DeepSeek 使用本地 registry endpoint。
3. BYOK 不接受用户 endpoint。
4. BYOK 缺 key 失败。
5. provider 返回非 JSON planner decision 时失败语义稳定。

### Client tests（客户端测试）

1. provider/model 两级选择正确更新 state。
2. custom model id 优先于下拉 model。
3. BYOK key save/update/delete 正常。
4. key 不进入 localStorage。
5. sendChat payload 不包含 endpoint/chat path/headers。

### Manual E2E（手动端到端）

1. Platform -> DeepSeek -> chat 成功 -> UI 显示 assistant decision -> quota 减少。
2. Platform -> Gemini -> chat 成功 -> UI 显示 assistant decision -> quota 减少。
3. BYOK -> DeepSeek -> chat 成功 -> UI 显示 assistant decision -> MongoDB quota 不减少。
4. 删除 BYOK key 后再次发送，前端或 core 返回明确错误。
5. 自定义 DeepSeek model id 可发送到 provider。

## 12. 风险与处理

1. Gemini response schema（响应结构）与 OpenAI-compatible response 不一致。  
   处理：Gemini adapter 必须只向上返回 normalized response。

2. 删除 mock 后本地开发门槛升高。  
   处理：测试使用 test adapter（测试适配器）；本地开发文档要求配置至少一个 provider key。

3. 真实 model id 更新频繁。  
   处理：registry 维护常用列表，同时 UI 支持 custom model id。

4. 旧 BYOK key 迁移可能误用。  
   处理：不自动迁移旧 key，需要用户重新保存 provider-scoped key。

5. Platform 和 BYOK 共用 UI 容易状态串扰。  
   处理：state 分开保存 `platformProvider/platformModel` 与 `byokProvider/byokModel`。

## 13. 验收标准

1. `server/app/api/routes/runtime.py` 不再返回 `entro-reasoning-v1` 作为默认平台模型。
2. server runtime path 不存在 `mock（模拟）` provider。
3. server provider 路由不再依赖全局 `llm_proxy_mode`。
4. Platform model panel 展示 DeepSeek 与 Google Gemini，并使用真实 model id。
5. BYOK model panel 初期只展示 DeepSeek。
6. 用户无法填写 endpoint/chat path/headers。
7. BYOK API key 被 encrypted storage（加密存储）持久化，可更新、删除。
8. Platform 请求扣 MongoDB quota；BYOK 请求不扣 MongoDB quota。
9. 全链路仍能返回 `AssistantDecisionTurn（助手决策轮次）` 并渲染到 Workspace 对话框。

