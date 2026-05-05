# 2026-05-05 Client Workspace 契约修复与能力补齐日志

本轮工作从 `client（客户端）` 的 Workspace 使用问题出发，最后发现核心矛盾不是单个按钮或单个 API 缺失，而是 `client / core / server / MongoDB / DashVector` 多层契约没有对齐。实际推进顺序是先审计并落盘改进清单，再按优先级把可见问题背后的契约补齐。

对应任务清单：

- `docs/tasks/2026-05-04_client_workspace_issue_audit_and_improvement_list.md`

## 关键判断

1. `credit（点数）` 显示为 0 的根因在服务端用户资料契约：UI 读 `credits_balance`，但权威额度已经迁到 `remaining_quota（剩余额度）`。
2. 上传入口不能把 `openFile（选择文件）` 和 `openDirectory（选择目录）` 混在一个 `Electron dialog（Electron 文件弹窗）` 中；部分桌面环境会退化成只能选目录。
3. `model（模型）` 列表不能由 client 硬编码，也不能由 `rate card（计费价目）` 间接决定；应来自 server runtime registry（运行时注册表）。
4. 素材删除不是简单移除数组项。为了避免重新 `segmenting（切分）/ vectorizing（向量化）`，需要 `soft delete（软删除）`，并让被删除素材的 `clip vector（片段向量）` 不参与 `retrieval（召回）`。
5. `BYOK（自带密钥）` 不应写死 `model name（模型名）` 和 endpoint（接口地址）；用户需要提供完整请求信息，包括 model、base URL、chat path、headers 和 API key。

## 处理结果

### 1. credit / quota 契约收口

完成 commit：

- `f4eaec9 fix: align credits with user quota`

主要变化：

1. `server` 的 `UserProfile（用户资料）` 增加 `quota_total / remaining_quota / quota_status`。
2. `credits_balance` 保留兼容，但优先映射到 `remaining_quota`。
3. `/api/v1/me` 读取用户时补齐 quota 默认值，并同步旧字段。
4. `AccountMenu（账号菜单）` 优先展示 `remaining_quota`，并增加 refresh（刷新）按钮。

这解决了 MongoDB 中 `quota_total=200000 / remaining_quota=199394`，但登录后 credit 显示为 0 的问题。

### 2. runtime model registry 与 planner mock

完成 commit：

- `2a7b083 fix: drive model list from runtime registry`

主要变化：

1. `server` 新增 `/api/v1/runtime/models`，返回平台实际可用 model（模型）列表。
2. client 不再硬编码平台 `gpt-4o / gemini-2.5-flash`。
3. 默认平台模型统一为 `entro-reasoning-v1`。
4. `mock chat（模拟聊天）` 输出改成符合 `PlannerDecisionModel（规划器决策模型）` 的 JSON，避免默认 mock 链路触发 `PLANNER_DECISION_INVALID`。

### 3. 上传文件与上传文件夹入口拆分

完成 commit：

- `4f063f6 fix: split media file and folder picker`

主要变化：

1. `Electron Main Process（主进程）` 新增两个 IPC：
   - `dialog:open-media-files`
   - `dialog:open-media-folder`
2. `preload（预加载脚本）` 暴露：
   - `showOpenMediaFiles()`
   - `showOpenMediaFolder()`
3. `electronBridge（Electron 桥）` 增加：
   - `pickVideoFilesFromElectron()`
   - `pickVideoFolderFromElectron()`
4. `Launchpad / Workspace` 上传入口展示两个明确选项：
   - `Select Videos（选择视频）`
   - `Select Folder（选择文件夹）`

### 4. 失败素材 retry

完成 commit：

- `6c7ec04 feat: retry failed asset ingest`

主要变化：

1. `core` 新增：
   - `POST /api/v1/projects/{project_id}/assets/{asset_id}:retry`
2. retry 会校验 `source_path（源路径）` 是否仍可访问。
3. retry 会重置素材处理状态、清理该素材旧 clips（片段），重新排 `media task（媒体任务）`。
4. Workspace 失败素材卡片增加 `Retry icon button（重试图标按钮）`。
5. 修复 `_run_assets_import()` 中 ready 阶段基于旧 draft（草稿）推进的问题，避免生成的 clips 被覆盖。

## 5. 素材 soft delete / restore 与向量召回过滤

完成 commit：

- `19dad01 feat: soft delete workspace assets`

主要变化：

1. `AssetModel（素材模型）` 增加：
   - `lifecycle_state: active | deleted`
   - `deleted_at`
   - `fingerprint`
   - `vector_index_state: none | active | inactive`
2. `core` 新增：
   - `DELETE /api/v1/projects/{project_id}/assets/{asset_id}`
   - `POST /api/v1/projects/{project_id}/assets/{asset_id}:restore`
3. `SQLite（嵌入式数据库）` assets 表补齐 lifecycle 与 vector state 字段。
4. Workspace 默认只展示 active assets（活跃素材），提供 deleted assets（已删除素材）切换与 restore（恢复）按钮。
5. `core/retrieval.py` 增加 `asset_state == "active"` filter（过滤器），并在本地二次过滤 deleted assets 的 clips。
6. `server` 新增：
   - `POST /v1/assets/vector-index-state`
7. vector docs（向量文档）写入时带上：
   - `asset_state`
   - `asset_active`
8. 重新导入命中同一 `fingerprint（指纹）` 的已删除 ready asset 时，直接 restore，不重复切分和向量化。

这个改动把“删除素材”从 UI 操作变成了完整的跨层 lifecycle contract（生命周期契约）。

## 6. BYOK 自定义请求配置

完成 commit：

- `4c74674 feat: support custom byok chat config`

主要变化：

1. Workspace 顶栏中 BYOK 从固定模型列表改成 `BYOK Custom（自定义）`。
2. UI 支持配置：
   - model
   - base URL
   - chat path
   - API key
   - headers JSON
3. `client -> core` 增加 headers：
   - `X-BYOK-Chat-Path`
   - `X-BYOK-Headers`
4. `core/agent.py` 根据用户配置构造 endpoint。
5. BYOK endpoint 增加基础安全校验：
   - 允许 `https`
   - `http` 仅允许 localhost development（本地开发）
   - 阻止 `169.254.169.254`
6. `X-BYOK-Headers` 只接受 JSON object（对象），并跳过 `Authorization / Content-Type / Host / Content-Length` 等保留 header。
7. API key 尽量写入 Electron `secure store（安全存储）`；普通浏览器环境只保存在当前 session（会话）内，不再写入 `localStorage（本地存储）`。

## 验证

最终回归验证：

```bash
cd client
npm run build
```

结果：通过。

```bash
cd core
source venv/bin/activate
python -m pytest \
  tests/test_server_toolchain_integration.py::CoreChatPlannerSkeletonTest::test_failed_asset_retry_requeues_media_task \
  tests/test_server_toolchain_integration.py::CoreChatPlannerSkeletonTest::test_asset_soft_delete_restore_and_reimport_reuses_ready_asset \
  tests/test_server_toolchain_integration.py::CoreChatPlannerSkeletonTest::test_byok_chat_uses_custom_endpoint_model_and_headers
```

结果：`3 passed`。

```bash
cd server
source venv/bin/activate
python -m pytest \
  tests/test_user_routes.py \
  tests/test_runtime_hardening.py \
  tests/test_chat_proxy.py \
  tests/test_vector_service.py::TestInsertDocs::test_updates_asset_vector_index_state \
  tests/test_vector_routes.py::TestVectorizeSuccess::test_vector_index_state_updates_successfully
```

结果：`21 passed`。

## 后续注意

1. `core` 仍有旧测试依赖不存在的 `/tmp/*.mp4` 或旧 `create_project(media)` 假设，后续应统一修掉 fixture（测试夹具）和导入契约。
2. `soft delete（软删除）` 已经覆盖默认 UI、local summary（本地摘要）和 retrieval filter（召回过滤），但 DashVector update（向量更新）在真实环境中还需要联调确认 update 语义是否完全符合预期。
3. BYOK 当前按 OpenAI-compatible chat completions（OpenAI 兼容聊天补全）请求体发送。非 OpenAI-compatible provider（非兼容供应商）后续应单独建 provider adapter（供应商适配器），不要继续把参数塞进通用 headers。
4. `credit/quota（点数/额度）` 短期已经兼容；长期应决定是否彻底废弃 `credits_balance` 字段，避免两个概念并存。
