# Server 部署 Secrets 与 Client 模型目录一致性检查日记

日期：`2026-05-05`

## 背景

在完成 `provider registry（供应商注册表）` 驱动的模型路由改造后，需要确认两件事：

1. `server` 部署到远程环境时，`GitHub repository secrets（仓库密钥）` 需要补哪些变量，尤其是 `DeepSeek API key`。
2. `client` 端模型面板展示的 `provider（供应商）` 与 `model（模型）` 是否完全来自 `server`，从而保持前后端一致。

## Server 部署 Secrets 结论

当前 `server/app/services/models/registry.py` 中的平台模型注册表包含：

- `deepseek`
  - `api_key_env`: `DEEPSEEK_API_KEY`
  - models: `deepseek-chat`, `deepseek-reasoner`
- `google_gemini`
  - `api_key_env`: `GOOGLE_API_KEY`
  - models: `gemini-2.5-flash`, `gemini-2.5-pro`

`server/app/core/config.py` 中当前默认模型是：

- `llm_default_model = deepseek-chat`

因此远程部署如果要让默认 Platform chat 路径可用，需要在 `repository secrets` 中新增：

- `DEEPSEEK_API_KEY`

当前已有 `GOOGLE_API_KEY` 时，Gemini provider 可以显示为 available，但由于默认 provider/model 是 DeepSeek，如果缺少 `DEEPSEEK_API_KEY`，默认 Platform chat 仍可能不可用。

## 当前 Deploy Workflow 发现的问题

检查 `.github/workflows/deploy-server.yml` 后发现：

1. workflow 已经校验并写入 `GOOGLE_API_KEY`。
2. workflow 还没有校验或写入 `DEEPSEEK_API_KEY`。
3. `.env.production` 里仍写着旧变量：

```env
LLM_PROXY_MODE=google_gemini
```

这个变量在新的 `provider registry` 架构下已经不再被 `server/app/core/config.py` 使用，应删除，避免误导部署配置。

建议后续修改 workflow：

1. 在 `Validate required deployment configuration` 步骤加入 `DEEPSEEK_API_KEY`。
2. 在 `Deploy on ECS` 的 env/envs 中透传 `DEEPSEEK_API_KEY`。
3. 在生成 `.env.production` 时写入：

```env
DEEPSEEK_API_KEY=${{ secrets.DEEPSEEK_API_KEY }}
GOOGLE_API_KEY=${{ secrets.GOOGLE_API_KEY }}
```

4. 删除旧的：

```env
LLM_PROXY_MODE=google_gemini
```

## Repository Secrets 清单

按当前 workflow 与 server 能力，部署相关 secrets 至少包括：

- `GH_PAT`: 推送/拉取 GHCR image。
- `SERVER_SSH_HOST`: 部署服务器地址。
- `SERVER_SSH_USER`: 部署服务器用户。
- `SERVER_SSH_KEY`: SSH 私钥。
- `AUTH_JWT_SECRET`: server JWT 签名密钥。
- `AUTH_GOOGLE_CLIENT_ID`: Google OAuth client id。
- `AUTH_GOOGLE_CLIENT_SECRET`: Google OAuth client secret。
- `AUTH_GITHUB_CLIENT_ID`: GitHub OAuth client id。
- `AUTH_GITHUB_CLIENT_SECRET`: GitHub OAuth client secret。
- `GOOGLE_API_KEY`: Gemini 平台模型与 inspect 能力使用。
- `DEEPSEEK_API_KEY`: DeepSeek 平台模型使用，也是当前默认 Platform chat provider 所需。
- `MONGODB_ATLAS_URI`: MongoDB 连接地址。
- `DASHSCOPE_API_KEY`: multimodal embedding 使用。
- `DASHVECTOR_API_KEY`: DashVector 检索使用。
- `DASHVECTOR_ENDPOINT`: DashVector endpoint。

此外 repository variables 仍需要：

- `SERVER_BASE_URL`
- `CORS_ALLOW_ORIGINS`

## Client 模型目录一致性检查

`client` 的 Platform 模型目录主链路如下：

1. `client/src/services/authClient.ts`
   - `fetchRuntimeModels()` 调用 `GET /api/v1/runtime/models`。
2. `client/src/store/useAuthStore.ts`
   - `refreshModelCatalog()` 读取 server 返回的 `providers`。
   - 写入 `platformProviders` 与 `platformModels`。
3. `client/src/pages/WorkspacePage.tsx`
   - Platform provider select 使用 `platformProviders.map(...)`。
   - Platform model select 使用当前 provider 的 `models`。

结论：Platform 模式下，正常加载成功后，provider/model 列表来自 `server` runtime catalog。

但当前还不能说“完全只从 server 获取”，原因是：

1. `client` 内仍有默认常量：
   - `DEFAULT_PLATFORM_PROVIDER = deepseek`
   - `DEFAULT_PLATFORM_MODEL = deepseek-chat`
2. `WorkspacePage` 在 `platformProviders.length === 0` 时会显示 fallback `DeepSeek / deepseek-chat`。
3. `server` 的 `RuntimeModelsResponse.default_provider/default_model` 当前固定为 `deepseek/deepseek-chat`，没有按实际 available provider 动态选择。

这意味着如果远程部署只有 `GOOGLE_API_KEY`、没有 `DEEPSEEK_API_KEY`：

- server 会返回 DeepSeek unavailable、Gemini available。
- client 可以展示 Gemini provider/model。
- 但默认选择仍可能落在 `deepseek/deepseek-chat`，用户需要手动切换，或者请求失败。

## BYOK 模型目录说明

BYOK 模式当前不是从 server 获取 provider/model，而是按产品约束固定在 client/core 本地维护：

- provider: `DeepSeek`
- models: `deepseek-chat`, `deepseek-reasoner`
- 支持 `custom model id（自定义模型标识）`
- endpoint 不暴露给用户，由 core 固定调用 `https://api.deepseek.com/chat/completions`

这个不属于一致性缺陷，而是当前设计目标：BYOK 初期只提供 DeepSeek 一种本地接入方案。

## 建议后续动作

优先级较高：

1. 给 GitHub repository secrets 新增 `DEEPSEEK_API_KEY`。
2. 修改 `.github/workflows/deploy-server.yml`，把 `DEEPSEEK_API_KEY` 纳入校验和 `.env.production`。
3. 删除 deploy workflow 中旧的 `LLM_PROXY_MODE=google_gemini`。

一致性增强：

1. server 的 `/api/v1/runtime/models` 可以把 `default_provider/default_model` 改成第一个 available provider/model。
2. client 在 Platform catalog 未加载成功时，不展示可误选的真实 provider/model fallback，而展示 disabled placeholder。
3. 如果默认 provider unavailable，client 应自动切换到 server 返回的第一个 available provider/model。

## 当前判断

当前 Platform 列表“加载成功后的展示”基本由 server runtime catalog 驱动；但严格意义上还不是完全 server-driven，因为 client 仍有默认/fallback 展示逻辑。

部署层面必须补 `DEEPSEEK_API_KEY`，否则当前默认 `deepseek-chat` 路径在远程环境不可用。
