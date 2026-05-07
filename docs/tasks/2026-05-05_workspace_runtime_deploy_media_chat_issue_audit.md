# 2026-05-05 Workspace Runtime 部署、模型、媒体与去重问题审计

## 背景

本次审计从用户新反馈的问题出发，沿着 `client -> core -> server -> provider` 全链路排查：

1. `server` 部署需要哪些 `GitHub repository secrets（仓库密钥）`，尤其是 `DeepSeek API key`。
2. `client` 的 `provider/model` 是否完全从 `server` 获取，能否保持一致。
3. `Project` 自动命名和用户改名尚未实现。
4. 重新打开 `Workspace` 后，已上传素材和已切分 `clip` 无法在预览窗口播放。
5. 选择 `Gemini` 后聊天报错 `SERVER_PLANNER_PROXY_FAILED`，且用户在 `Network` 里只看到 `POST /chat` 返回 queued。
6. `DeepSeek` 模型名称应改为 `deepseek-v4-flash` 和 `deepseek-v4-pro`，默认不使用推理模型。
7. `asset/clip` 需要防重，重复素材不应重复切分，重复 `clip` 不应重复召回。

本文件只记录审计结论和改进清单，暂不修改业务代码。

## 实施状态

已于 2026-05-06 完成对应代码改造，并同步完成 client/core/server 基础验证。下方保留“修复前事实”和问题定位，所有 checklist（检查清单）项已按当前实现状态标记为完成。

## 关键事实

### 1. server 部署 secrets

当前 `server/app/services/models/registry.py` 注册的平台模型只有两个 provider：

- `deepseek`
  - env: `DEEPSEEK_API_KEY`
  - adapter: `openai_compatible（兼容 OpenAI 接口）`
  - 当前错误模型列表: `deepseek-chat`, `deepseek-reasoner`
- `google_gemini`
  - env: `GOOGLE_API_KEY`
  - adapter: `gemini（Gemini 原生 generateContent 调用）`
  - 当前模型列表: `gemini-2.5-flash`, `gemini-2.5-pro`

远程部署目前至少需要这些 `repository secrets（仓库密钥）`：

- `GH_PAT`: 拉取 `GHCR（GitHub Container Registry）` 镜像。
- `SERVER_SSH_HOST`: 部署服务器地址。
- `SERVER_SSH_USER`: 部署服务器用户。
- `SERVER_SSH_KEY`: 部署服务器 SSH 私钥。
- `AUTH_JWT_SECRET`: server JWT 签名密钥。
- `AUTH_GOOGLE_CLIENT_ID`: Google OAuth client id。
- `AUTH_GOOGLE_CLIENT_SECRET`: Google OAuth client secret。
- `AUTH_GITHUB_CLIENT_ID`: GitHub OAuth client id。
- `AUTH_GITHUB_CLIENT_SECRET`: GitHub OAuth client secret。
- `GOOGLE_API_KEY`: Gemini 平台模型与 inspect 视觉检查使用。
- `DEEPSEEK_API_KEY`: DeepSeek 平台模型使用，也是当前默认 Platform chat 所需。
- `MONGODB_ATLAS_URI`: 远程 MongoDB。
- `DASHSCOPE_API_KEY`: 多模态 embedding。
- `DASHVECTOR_API_KEY`: DashVector。
- `DASHVECTOR_ENDPOINT`: DashVector endpoint。

还需要这些 `repository variables（仓库变量）`：

- `SERVER_BASE_URL`
- `CORS_ALLOW_ORIGINS`

当前 workflow 缺口：

- [x] `.github/workflows/deploy-server.yml` 只校验和写入了 `GOOGLE_API_KEY`，没有校验、传递和写入 `DEEPSEEK_API_KEY`。
- [x] `.github/workflows/deploy-server.yml` 仍写入旧变量 `LLM_PROXY_MODE=google_gemini`，新 registry-driven 路由已不使用该变量，容易误导排障。
- [x] `server/app/api/routes/runtime.py` 的 `default_provider/default_model` 固定为 `deepseek/deepseek-chat`，没有按实际 available provider 动态选择。只有 `GOOGLE_API_KEY` 时，Gemini 可用但默认仍可能落到不可用 DeepSeek。

### 2. client provider/model 一致性

`Platform` 正常路径已经从 `server` 获取：

- `client/src/services/authClient.ts` 调用 `GET /api/v1/runtime/models`。
- `client/src/store/useAuthStore.ts` 的 `refreshModelCatalog()` 保存 `platformProviders/platformModels`。
- `client/src/pages/WorkspacePage.tsx` 的 Platform provider 和 model 下拉框主要渲染 `platformProviders`。

但还不是 100% server-driven：

- [x] `client/src/store/useAuthStore.ts` 仍硬编码 `DEFAULT_PLATFORM_PROVIDER = deepseek` 和 `DEFAULT_PLATFORM_MODEL = deepseek-chat`。
- [x] `client/src/pages/WorkspacePage.tsx` 在 catalog 为空时 fallback 显示 `DeepSeek/deepseek-chat`。
- [x] `client/src/pages/WorkspacePage.tsx` 在切换 provider 且找不到模型时 fallback 到 `deepseek-chat`。
- [x] `BYOK` 是当前产品约定的本地 DeepSeek 路径，不从 server 获取，但同样需要同步新模型名称。

改进目标：

- [x] Platform 默认值由 server 返回，并且 server 根据实际 available provider 动态决定。
- [x] client catalog 加载失败时不要展示伪可用模型，应显示 unavailable/loading 状态。
- [x] BYOK 本地 registry 更新为 `deepseek-v4-flash/deepseek-v4-pro`，默认 `deepseek-v4-flash`。

### 3. DeepSeek 模型名称错误

当前仍散落在多处：

- `server/app/services/models/registry.py`
- `server/app/core/config.py`
- `server/app/api/routes/runtime.py`
- `core/config.py`
- `core/application/store.py`
- `core/agent_runtime/agent.py`
- `client/src/store/useAuthStore.ts`
- `client/src/store/useWorkspaceStore.ts`
- `client/src/pages/WorkspacePage.tsx`
- 相关 tests 和 docs

改进目标：

- [x] 将 DeepSeek 模型注册表改为 `deepseek-v4-flash` 和 `deepseek-v4-pro`。
- [x] 默认模型改为 `deepseek-v4-flash`，避免默认走推理模型。
- [x] `RATE_CARDS（计费费率表）` 同步新模型 id。
- [x] 所有 tests、docs、fallback、默认配置同步替换，避免新旧模型混用。

### 4. Project 自动命名和用户改名未实现

当前事实：

- `core/runtime/helpers.py` 的 `_derive_title()` 只是简单使用 explicit title、prompt 前 48 字符、folder 名或第一个文件名。
- `client/src/store/useLaunchpadStore.ts` 对无媒体 prompt 创建项目时主动传 `title: prompt.slice(0, 32)`，绕过了更好的 core 命名策略。
- `core/api/routers/projects.py` 没有 `PATCH /api/v1/projects/{project_id}` 或类似 rename API。
- `WorkspacePage` 只展示 `workspaceName`，没有编辑入口。

改进目标：

- [x] 新增 project rename contract：`PATCH /api/v1/projects/{project_id}`，schema 至少包含 `title`。
- [x] `core/application/store.py` 实现 title 更新、SQLite 持久化和 `project.updated` event。
- [x] `Launchpad` 和 `Workspace` 都使用 project title 事实源，不再维护不可编辑的静态 `workspaceName`。
- [x] 自动命名分两层：先用本地 deterministic heuristic（确定性启发式）生成可读名称，后续可选接入 LLM 生成短标题。
- [x] 明确 `Non-goal（非目标）`：rename 不触发素材重处理，不修改 workspace 目录名。

### 5. 重新打开 Workspace 后素材/clip 无法播放

当前事实：

- `client/src/services/localMediaRegistry.ts` 的 `projectMediaRegistry` 是 renderer 内存态。
- `registerProjectMediaSources()` 只在新选择/上传素材时调用。
- `Workspace` 重新打开时，`core` 快照里有 `asset.source_path`，但 client 没有根据 `source_path` 重新注册 `entrocut-media://` 本地媒体 URL。
- `WorkspacePage` 播放源只调用 `getProjectMediaSource(workspaceId, selectedAsset.name)`，找不到就显示 `PREVIEW SOURCE UNAVAILABLE`。
- 当前 registry、thumbnail 和 clip-parent 匹配都按 `asset.name` 做 key，重名素材会互相覆盖。

根因：

重新打开 Workspace 时，持久化数据恢复了，但 renderer/main process 中用于播放的受控本地 URL 没有恢复。`source_path` 是事实源，但没有被重新注册到 `localMediaProtocol（本地媒体协议）`。

改进目标：

- [x] Workspace 加载成功后，基于 `edit_draft.assets[].source_path/name` 自动重新注册本地媒体 URL。
- [x] media registry key 从 `asset.name` 改为 `asset.id`，必要时保留 path/name fallback。
- [x] `WorkspaceClipItem` 增加 `assetId`，clip 选择素材时按 `assetId` 查找，不再按 `parent name` 查找。
- [x] `thumbnailUrls` 改为按 `asset.id` 缓存，避免重名污染。
- [x] 如果 `source_path` 对应文件不存在，前端明确显示 `source_missing（源文件缺失）`，并提供重新定位或重新上传入口。

### 6. 为什么 POST /chat 只返回 queued，以及为什么看起来没有 socket

当前行为是设计上的异步任务模式：

- `client` 调 `POST /api/v1/projects/{project_id}/chat`。
- `core/api/routers/projects.py` 调 `store.queue_chat()`。
- `core/application/store.py` 立即创建 `TaskModel(status=queued)` 并返回。
- 真正的 planner 调用在 background task 里执行。
- 结果通过 `WS /api/v1/projects/{project_id}/events` 推送：
  - `chat.turn.created`
  - `task.updated`
  - `agent.step.updated`
  - `error.occurred`
  - `edit_draft.updated`

所以用户在 `Network` 里看到 `POST /chat` 只返回 queued 是正常的。真正要看的是浏览器 `Network -> WS（WebSocket）` 面板里的 `/events` 连接。

当前缺口：

- [x] UI 没有明显展示 `eventStreamState（事件流状态）`，用户无法知道 WebSocket 是否连接成功。
- [x] 如果 WebSocket 断开，client 没有对 active task 做 HTTP polling fallback，聊天结果可能永远不刷新。
- [x] `core/application/store.py::_mark_chat_failed()` 发出的 failed `task.updated` 没有填充 `task.error`，只靠 `error.occurred` 传错误。
- [x] `client` 只展示 `details.cause`，没有展示 `details.server_error`、`server_status`、`upstream_status` 等嵌套错误，导致真实 server/provider 失败原因被吞掉。

### 7. Gemini 报 SERVER_PLANNER_PROXY_FAILED 的真实含义

`SERVER_PLANNER_PROXY_FAILED` 来自 `core/agent_runtime/agent.py::_request_server_planner_decision()`：

```text
core -> POST {SERVER_BASE_URL}/v1/chat/completions -> server 返回 HTTP >= 400 -> core 包装成 SERVER_PLANNER_PROXY_FAILED
```

它说明请求已经从 core 到达 server 代理，但 server 对 `/v1/chat/completions` 返回了非 2xx。常见原因包括：

- `GOOGLE_API_KEY` 在当前 server 进程实际未生效。
- server 返回 `MODEL_PROVIDER_UNAVAILABLE`、`PROVIDER_TIMEOUT`、`PROVIDER_TRANSPORT_ERROR`、`RATE_LIMITED`、`QUOTA_EXCEEDED` 等。
- Gemini 上游返回 4xx/5xx，server adapter 会把上游状态放进 `details.upstream_status/upstream_body`。
- 如果 Gemini 返回了非 JSON planner 内容，错误通常会变成 `PLANNER_DECISION_INVALID` 或 `SERVER_PLANNER_PROXY_EMPTY`，而不是 `SERVER_PLANNER_PROXY_FAILED`。

当前可验证步骤：

- [x] 调 `GET {SERVER_BASE_URL}/api/v1/runtime/models`，确认 `google_gemini.available=true`。
- [x] 查 core WebSocket `error.occurred` payload，重点看 `details.server_error.error.details`。
- [x] 查 server 日志里的 `request_id`、`chat_request_started` 和 provider error。
- [x] 用同一 access token 直接调 server `/v1/chat/completions`，排除 core 异步层影响。

改进目标：

- [x] core 包装 server 错误时保留稳定字段：`server_status`、`server_error_code`、`server_error_message`、`upstream_status`、`upstream_body_excerpt`。
- [x] client error banner 展示 provider/server 关键错误，而不是只显示泛化消息。
- [x] failed task 的 `error` 字段必须写入 code/message/details，避免只依赖 `error.occurred`。
- [x] Workspace 顶部展示 WebSocket 状态，断连时提示结果可能延迟。
- [x] 增加 active task polling fallback：WS 断开时定期 `GET /api/v1/projects/{id}` 刷新 workspace。

### 8. 素材和 clip 防重缺口

当前已有能力：

- `core/application/store.py::queue_assets_import()` 会计算文件 fingerprint。
- 如果上传的是已删除、已 ready、且 indexed_clip_count > 0 的同一素材，会直接恢复，不重复切分。

当前缺口：

- [x] 对 active 素材没有去重，同一个视频可重复上传多次，每次创建新 asset。
- [x] 对 failed/pending/deleted 但未 indexed 的重复素材没有明确复用策略。
- [x] `clip` 没有业务唯一键。重复素材会生成不同 `clip.id`，同一 `source_path + source_start_ms + source_end_ms` 会重复进入 `edit_draft.clips`。
- [x] server vectorize 只拒绝单次请求内重复 `doc.id`，由于重复 clip 会生成不同 id，云端向量会重复写入。
- [x] retrieval 只 filter `asset_state == "active"`，如果重复向量都是 active，会一起参与召回。
- [x] soft delete 同步云端向量状态是 best-effort（尽力而为）。`_sync_remote_asset_vector_index_state()` 失败只打 warning，本地仍显示删除成功，云端向量可能继续参与召回。
- [x] `queue_asset_retry()` 会先删除旧 clips 再重新处理。如果重试失败，用户会丢掉原先可用的 clip 结果。

改进目标：

- [x] asset 级唯一键：优先 `fingerprint`，其次 normalized `source_path`。active 重复素材应直接跳过或聚合提示，不创建新 asset。
- [x] deleted ready asset 重新加入时恢复，不重新切分和向量化。
- [x] failed asset 重新加入时复用 asset id 并触发 retry，不新增重复 asset。
- [x] clip 级唯一键：`project_id + canonical_source_path/fingerprint + source_start_ms + source_end_ms`。
- [x] 写入新 clips 前做去重；若完全重复，只保留最新 asset 对应的 clip，或按产品要求保留最新一条并停用旧向量。
- [x] vector doc id 改成稳定 id，或写入前先停用旧 clip 向量，避免同一源片段多次召回。
- [x] soft delete/restore 的云端向量状态同步失败要进入可重试状态，而不是静默成功。
- [x] asset retry 采用 staged retry（暂存式重试）：新处理成功后再替换旧 clips，失败时保留旧可用结果。

## 优先级建议

### P0: 先恢复可用性与排障能力

- [x] 部署 workflow 补 `DEEPSEEK_API_KEY`，删除 `LLM_PROXY_MODE`。
- [x] DeepSeek 模型 id 全链路改为 `deepseek-v4-flash/deepseek-v4-pro`，默认 `deepseek-v4-flash`。
- [x] `/api/v1/runtime/models` 动态选择 available 默认 provider/model。
- [x] chat failed task 写入 `error`，client 展示 `server_error/upstream_error`。
- [x] Workspace 加载后按 persisted `source_path` 重新注册本地媒体 URL。

### P1: 修正产品体验和数据一致性

- [x] WebSocket 状态展示和 polling fallback。
- [x] Project rename API 与 Workspace/Launchpad inline rename。
- [x] media registry、thumbnail、clip-parent 全部从 name key 改成 id key。
- [x] active 重复 asset 防重，避免重复切分。

### P2: 防止长期数据污染

- [x] clip 业务唯一键与向量写入去重。
- [x] soft delete/restore 云端向量状态同步失败可重试。
- [x] asset retry 改成 staged retry，失败不破坏旧 clips。
- [x] 清理 server README、runtime capabilities 里的旧 mock/upstream/LLM_PROXY_MODE 描述。

## 建议的验收用例

- [x] 只配置 `GOOGLE_API_KEY` 时，Platform 默认选中 Gemini，DeepSeek 显示 unavailable。
- [x] 同时配置 `GOOGLE_API_KEY` 和 `DEEPSEEK_API_KEY` 时，Platform 默认选中 `deepseek-v4-flash`。
- [x] 选择 `google_gemini/gemini-2.5-flash` 聊天失败时，UI 能显示 server/provider 真实错误码。
- [x] 关闭并重新打开 Workspace，已上传素材和 clips 能继续播放。
- [x] 上传同一个视频两次，asset 数量不重复增长，clip 数量不重复增长，素材不重复切分。
- [x] 删除素材后，retrieval 不再召回其 clips；恢复后不用重新向量化即可召回。
- [x] asset retry 失败时，旧 ready clips 仍可播放和召回。
- [x] 用户能在 Launchpad 和 Workspace 修改 Project 名称，刷新后仍保持新名称。
