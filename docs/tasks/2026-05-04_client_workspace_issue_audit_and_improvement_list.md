# Client Workspace（客户端工作台）问题排查与逻辑改进清单

日期：`2026-05-04`

## 1. 范围

本文件从 `client（客户端）` 入口开始，追到 `core（本地引擎）`、`server（服务端）`、`MongoDB（文档数据库）` 与 `DashVector（向量库）` 的实际契约，整理以下问题的根因与改进清单：

1. `Launchpad（启动台）/ Workspace（工作台）` 上传入口只能选择文件夹，不能选择单个视频。
2. `Workspace（工作台）` 需要支持删除视频素材，优先 `soft delete（软删除）`。
3. `MongoDB（文档数据库）` 里 `quota_total=200000 / remaining_quota=199394`，登录后 `credit（点数）` 显示为 `0`。
4. 素材 `segmenting（切分）/ vectorizing（向量化）` 失败后，用户缺少刷新或重试手段。
5. `server（服务端）` 真正支持的 `model（模型）` 与 `client（客户端）` 面板显示的 `gpt-4o` mock 列表不一致，模型调用链路不通。
6. `BYOK（自带密钥）` 模式需要允许用户填写完整模型请求信息，而不是写死 `model name（模型名）` 和 `endpoint（接口地址）`。

## 2. 一句话结论

当前最大问题不是单点 UI 缺失，而是多处 `contract（契约）` 不一致：`client（客户端）` 暴露了用户可见能力，但 `core（本地引擎）/ server（服务端）` 没有对应的稳定 `API（接口）`、状态字段和刷新入口。应先收敛 `asset lifecycle（素材生命周期）`、`quota/credit（额度/点数）`、`model routing（模型路由）` 三个核心契约，再补 UI。

## 3. 当前证据

### 3.1 上传入口

`client/main/fileScanner.ts:154-171` 当前只有一个 `dialog:open-media`，并把 `openFile（选择文件）`、`openDirectory（选择目录）`、`multiSelections（多选）` 混在同一个 `Electron dialog（Electron 文件弹窗）`：

```ts
properties: ["openFile", "openDirectory", "multiSelections"]
```

`client/src/services/electronBridge.ts:108-117` 只暴露 `pickMediaFromElectron()`，没有区分选择文件和选择文件夹。

这类混合 `dialog（弹窗）` 在部分 Linux/portal/桌面环境下会退化成目录选择器，所以用户看到只剩 `Select Folder（选择文件夹）` 是合理现象。

### 3.2 删除与重试

`WorkspacePage（工作台页面）` 的素材卡片只展示状态，没有删除、恢复、重试操作：

- 上传入口：`client/src/pages/WorkspacePage.tsx:591-605`
- 失败展示：`client/src/pages/WorkspacePage.tsx:741-784`

`core/routers/projects.py` 目前只有：

- `POST /api/v1/projects/{project_id}/assets:import`
- `POST /api/v1/projects/{project_id}/chat`
- `POST /api/v1/projects/{project_id}/export`

没有 `delete asset（删除素材）`、`restore asset（恢复素材）`、`retry asset（重试素材）` 级别的 `API（接口）`。

`core/store.py:902-948` 会把导入失败的素材标成 `failed`，但没有暴露重新入队能力。

### 3.3 credit 显示为 0

`client/src/services/authClient.ts:30-37` 的 `AuthUser（登录用户）` 只读 `credits_balance`。

`client/src/components/account/AccountMenu.tsx:120-122` 右上角 `Credits（点数）` 也只展示 `authUser.credits_balance`。

`server/app/services/auth/users.py:73-81` 的 `user_profile()` 只返回：

```py
"credits_balance": int(user.get("credits_balance") or 0)
```

但 `quota（额度）` 新逻辑在 `server/app/services/quota.py:128-140`，字段是：

- `quota_total`
- `remaining_quota`
- `quota_status`

所以当 `MongoDB（文档数据库）` 用户文档只有 `quota_total/remaining_quota`，但没有 `credits_balance` 时，`/api/v1/me` 会稳定返回 `credits_balance=0`。这不是 client 缓存问题，而是字段契约错位。

### 3.4 model 链路

`client/src/pages/WorkspacePage.tsx:642-658` 硬编码了：

- `gpt-4o-mini`
- `gpt-4o`
- `BYOK gpt-4o-mini`
- `BYOK gpt-4o`

`client/src/store/useWorkspaceStore.ts:1294-1312` 会把选中的 `model（模型）` 传给 `core（本地引擎）`。

`core/config.py:7-11` 的平台默认模型却是：

- `SERVER_CHAT_MODEL=entro-reasoning-v1`
- `DEFAULT_BYOK_BASE_URL=https://api.openai.com`

`server/app/core/config.py:61-78` 的真实配置是：

- `llm_proxy_mode=mock` 默认。
- `llm_default_model=entro-reasoning-v1`。
- `llm_gemini_default_model=gemini-2.5-flash`。
- `dashscope_multimodal_embedding_model=qwen3-vl-embedding`。

`server/app/services/gateway/provider_routing.py:17-55` 真正只支持两类真实 `provider（模型供应商）`：

1. `google_gemini`：使用 `GOOGLE_API_KEY` 和 Gemini 的 `OpenAI-compatible endpoint（OpenAI 兼容接口）`。
2. `upstream`：使用 `llm_upstream_base_url / llm_upstream_api_key / llm_upstream_chat_path`。

默认 `mock（模拟）` 模式不是一个 provider；它会在 `server/app/services/gateway/chat_proxy.py` 生成普通自然语言 mock 内容。但 `core/agent.py:330-350` 期望模型返回 `PlannerDecisionModel（规划器决策模型）` 的 JSON。也就是说，默认 `mock chat（模拟聊天）` 很可能会触发 `PLANNER_DECISION_INVALID`，这是“模型链路不通”的关键原因之一。

### 3.5 BYOK 当前能力

`client/src/store/useAuthStore.ts:25-62` 已保存：

- `selectedModel`
- `routingMode`
- `byokKey`
- `byokBaseUrl`

但 `WorkspacePage（工作台页面）` 只显示 `BYOK API Key（自带密钥）` 输入框，没有显示 `base URL（基础地址）`、`endpoint path（接口路径）`、自定义 `model（模型）`。

`client/src/services/coreClient.ts:500-508` 只给 `core（本地引擎）` 传：

- `X-Routing-Mode`
- `X-BYOK-Key`
- `X-BYOK-BaseURL`

`core/agent.py:274-284` 在 `BYOK（自带密钥）` 模式下固定把地址拼成：

```py
endpoint_url = f"{base_url}/v1/chat/completions"
```

因此当前 `BYOK（自带密钥）` 只能覆盖 `base URL（基础地址）` 和 `API key（接口密钥）`，不能覆盖完整 `endpoint（接口地址）`、`model（模型）`、`headers（请求头）` 或 `provider type（供应商类型）`。

另外，`byokKey` 当前随 `MODEL_PREFS_KEY` 存在 `localStorage（本地存储）`，不应长期这样保存密钥。

## 4. 改进清单

### P0. 修复 credit / quota 契约

目标：用户看到的 `Credits（点数）` 必须与 `MongoDB（文档数据库）` 中的权威额度一致。

建议：

1. 统一命名：短期把 UI 的 `Credits（点数）` 映射到 `remaining_quota（剩余额度）`；长期再决定是否保留 `credits_balance`。
2. `server/app/schemas/user.py` 扩展 `UserProfile（用户资料）`：
   - `quota_total: int`
   - `remaining_quota: int`
   - `quota_status: string`
   - 保留 `credits_balance` 作为兼容字段，值可先等于 `remaining_quota`。
3. `UserService.user_profile()` 和 `usage_snapshot()` 不再只读 `credits_balance`，而是优先读 `remaining_quota`。
4. `get_current_user()` 或 `/api/v1/me` 内调用 `QuotaService.ensure_user_quota_defaults()`，确保老用户文档补齐字段。
5. `client/src/services/authClient.ts` 扩展 `AuthUser（登录用户）` 类型，`AccountMenu（账号菜单）` 优先展示 `remaining_quota`。
6. `useAuthStore（认证状态）` 增加 `refreshUser()`：调用 `fetchCurrentUser()`，把最新 `MongoDB（文档数据库）` 用户数据写回 store。
7. `AccountMenu（账号菜单）` 增加 `RefreshCw icon button（刷新图标按钮）`，点击后触发 `refreshUser()`，显示 `refreshing/error` 状态。

验收：

1. 给测试用户只设置 `quota_total=200000 / remaining_quota=199394`，不设置 `credits_balance`。
2. 登录后右上角显示约 `199k`，不是 `0`。
3. 手动改 MongoDB `remaining_quota` 后点击刷新按钮，UI 更新。

### P0. 修复平台模型列表与 planner mock

目标：`client（客户端）` 展示的 `model（模型）` 来自 `server（服务端）` 真实能力，不再硬编码 `gpt-4o`。

建议：

1. 扩展 `GET /api/v1/runtime/capabilities` 或新增 `GET /api/v1/runtime/models`，返回：
   - `platform_models`: `[{ id, label, available, route, upstream_model? }]`
   - `default_model`
   - `provider_mode`
   - `warnings`
2. 平台默认只展示 `entro-reasoning-v1` 这一类 `virtual model name（虚拟模型名）`。
3. `server（服务端）` 内部再把 `entro-reasoning-v1` 映射到：
   - `mock`：专门返回合法 `PlannerDecisionModel（规划器决策模型）` JSON。
   - `google_gemini`：默认 `gemini-2.5-flash`。
   - `upstream`：`llm_upstream_default_model` 或请求传入模型。
4. 如果 `llm_proxy_mode=mock`，mock 输出必须符合 `core/agent.py` 的 planner JSON 契约，不能再返回普通编辑建议文本。
5. `client（客户端）` 模型下拉从 runtime API 动态加载；没有可用真实 provider 时，展示 `mock planner` 或禁用编辑型 chat。
6. `rate card（计费价目）` 不应决定 UI 模型列表；`RATE_CARDS` 只负责计费。

验收：

1. 默认本地 `mock` 模式下，发送 chat 不再触发 `PLANNER_DECISION_INVALID`。
2. `google_gemini` 模式下，client 仍显示 `entro-reasoning-v1`，server 内部使用 `gemini-2.5-flash`。
3. client 不再硬编码 `gpt-4o/gpt-4o-mini` 作为平台模型。

### P0. 拆分上传文件与上传文件夹入口

目标：既能选择单个或多个视频文件，也能选择整个文件夹。

建议：

1. `Electron main（Electron 主进程）` 新增两个 IPC：
   - `dialog:open-media-files`：`properties=["openFile","multiSelections"]`，带 video filter。
   - `dialog:open-media-folder`：`properties=["openDirectory"]`，选择后递归扫描视频。
2. 保留现有 `dialog:open-media` 作为兼容入口，但新 UI 不再依赖混合 dialog。
3. `preload（预加载脚本）` 暴露：
   - `showOpenMediaFiles()`
   - `showOpenMediaFolder()`
4. `electronBridge（Electron 桥）` 暴露：
   - `pickVideoFilesFromElectron()`
   - `pickVideoFolderFromElectron()`
5. `Launchpad（启动台）/ Workspace（工作台）` 点击上传时弹出一个小菜单：
   - `Select Videos（选择视频）`
   - `Select Folder（选择文件夹）`
6. 拖拽仍走现有统一归一化逻辑。

验收：

1. 在 `Launchpad（启动台）` 点击上传，可以选单个 `.mp4`。
2. 在 `Workspace（工作台）` 点击上传，可以选多个视频。
3. 可以选择文件夹并递归导入视频。
4. 原有 `drag/drop（拖拽）` 不回归。

### P1. 增加素材 soft delete / restore

目标：删除素材不破坏已有切分和向量化结果；重新加回来时可复用；删除素材的 `clip vector（片段向量）` 不参与云端 `retrieval（召回）`。

建议契约：

1. `AssetModel（素材模型）` 增加：
   - `lifecycle_state: "active" | "deleted"`
   - `deleted_at?: string`
   - `fingerprint?: string`
   - `vector_index_state?: "none" | "active" | "inactive"`
2. `ClipModel（片段模型）` 保持不物理删除；UI 和能力派生默认只看 `active assets（活跃素材）` 的 clips。
3. `core（本地引擎）` 增加：
   - `DELETE /api/v1/projects/{project_id}/assets/{asset_id}`
   - `POST /api/v1/projects/{project_id}/assets/{asset_id}:restore`
4. `server（服务端）` 增加向量可见性接口：
   - `POST /v1/assets/vector-index-state`
   - 入参：`project_id`, `asset_id`, `active`
   - 作用：把云端向量元数据置为 active/inactive，或维护可被 retrieval filter 使用的索引状态。
5. `core/retrieval.py` 的 filter 不能只用 `project_id == "..."`，需要加入 active 过滤条件。当前 `core/retrieval.py:39` 只按 `project_id` 过滤，会让被删除素材仍进入候选池。
6. 重新导入时先计算 `fingerprint（指纹）`：
   - 短期：`source_path + size + mtime_ns`
   - 长期：内容 hash 或分段 hash
7. 如果命中已删除且已完成向量化的素材，直接 `restore（恢复）`，不要重新切分和向量化。

验收：

1. 删除素材后，素材卡片从默认列表消失，clip 列表不再显示其 clips。
2. 删除素材后发起 `retrieval（召回）`，云端不会返回该素材的 clips。
3. 重新添加同一素材，不重复 `segmenting/vectorizing（切分/向量化）`。
4. 恢复后该素材重新参与 `retrieval（召回）`。

### P1. 增加素材失败重试

目标：素材处理失败后，用户可以从 UI 重新触发。

建议：

1. `core（本地引擎）` 增加：
   - `POST /api/v1/projects/{project_id}/assets/{asset_id}:retry`
2. `retry（重试）` 行为：
   - 校验素材存在且 `source_path` 仍可访问。
   - 清理该素材旧的失败状态。
   - 重新排一个 `media task（媒体任务）`。
   - 如果有稳定 clips，可支持从 `vectorizing（向量化）` 阶段恢复；第一版可从 `segmenting（切分）` 重新跑。
3. `WorkspacePage（工作台页面）` 对 `processingStage === "failed"` 的素材展示：
   - `Retry icon button（重试按钮）`
   - `Delete icon button（删除按钮）`
   - `lastError（最后错误）` tooltip 或详情。
4. `core/store.py` 当前还有一个相关风险：`ready_draft` 在 `core/store.py:857-866` 使用的是旧 `draft`，而不是前面追加过 `new_clips` 的 `vectorizing_draft`。这可能导致 ready 阶段状态覆盖掉已生成的 clips。重试实现前应先修正为基于最新 draft 状态推进。
5. `server（服务端）` 的 `/v1/assets/vectorize` 最好具备 `idempotent（幂等）` 语义：同一个 `doc.id` 重试时应 upsert 或安全覆盖，而不是因重复插入失败。

验收：

1. 模拟 `vectorize（向量化）` 返回 500，素材显示失败和错误原因。
2. 点击重试后，任务重新进入 `segmenting/vectorizing`。
3. 重试成功后素材进入 `ready`，clip 数和 indexed clip 数正确。

### P1. 扩展 BYOK 请求配置

目标：用户能填写完整 OpenAI-compatible 请求信息，而不是只能填 API key。

第一版边界：只支持 `OpenAI-compatible（OpenAI 兼容）` `chat completions（聊天补全）`，不支持任意 provider 私有协议。

建议 `BYOKConfig（自带密钥配置）`：

```ts
interface BYOKConfig {
  providerType: "openai_compatible";
  model: string;
  baseUrl: string;
  chatPath: string; // 默认：/v1/chat/completions
  apiKeyRef: string; // secure store key（安全存储键），不是 localStorage（本地存储）里的明文 key
  headers?: Record<string, string>;
  timeoutSeconds?: number;
}
```

改动：

1. `client（客户端）` UI 增加表单：
   - `Model（模型）`
   - `Base URL（基础地址）`
   - `Chat Path（聊天接口路径）`
   - `API Key（接口密钥）`
   - 可选 `Headers（请求头）`
2. `byokKey` 使用 `Electron secure store（Electron 安全存储）`，不要保存在 `localStorage（本地存储）`。
3. `core（本地引擎）` 接收 `X-BYOK-Chat-Path` 或请求 body 中的 `routing` 对象，不再写死 `/v1/chat/completions`。
4. `core（本地引擎）` 对 `baseUrl/chatPath` 做 `allowlist（允许列表）` 式校验：
   - 只允许 `https://`，本地开发可允许 `http://127.0.0.1`。
   - 禁止内网元数据地址，避免 `SSRF（服务端请求伪造）`。
5. `test connection（测试连接）`：发送轻量 mock planner prompt，校验返回可解析为 planner JSON。

验收：

1. 用户可填任意 OpenAI-compatible provider 的 `base URL + path + model + key`。
2. `core（本地引擎）` 实际请求地址与用户输入一致。
3. 关闭 app 重启后，密钥仍在 secure store，不出现在 `localStorage`。

## 5. 推荐实施顺序

1. P0-1：修复 `credit/quota（点数/额度）` 契约和刷新按钮。
2. P0-2：把 `model list（模型列表）` 改成 `runtime-driven（运行时驱动）`，并修复 mock planner JSON。
3. P0-3：拆分 `Select Videos（选择视频）` 和 `Select Folder（选择文件夹）`。
4. P1-1：实现 `asset retry（素材重试）`，同时修正 `ready_draft` 使用旧 draft 的风险。
5. P1-2：实现 `asset soft delete（素材软删除）` 和云端向量 active/inactive。
6. P1-3：扩展 `BYOK（自带密钥）` 完整配置与 secure store。

## 6. Non-goals（非目标）

1. 不上传原始视频到 `server（服务端）`。
2. 不在第一版支持所有私有 provider 协议；`BYOK（自带密钥）` 先收敛到 `OpenAI-compatible（OpenAI 兼容）`。
3. 不做物理删除向量作为第一选择；优先 `soft delete（软删除）` + active filter，以便恢复和复用。
4. 不把 `rate card（计费价目）` 当作 `model registry（模型注册表）`。
