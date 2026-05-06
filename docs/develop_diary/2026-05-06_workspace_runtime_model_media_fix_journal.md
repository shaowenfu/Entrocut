# 2026-05-06 Workspace Runtime、模型与媒体链路修复日记

## 背景

本轮工作承接 `docs/tasks/2026-05-05_workspace_runtime_deploy_media_chat_issue_audit.md` 的问题清单，目标不是做单点修补，而是把 `client -> core -> server -> provider` 这条链路里已经暴露出来的契约不一致、错误不可见、数据重复和部署变量缺口一起收敛。

用户后续确认，登录阶段的 `login-sessions` 失败属于网络问题，因此本文不把该问题作为代码缺陷展开，只记录上一轮已经完成的业务链路改进。

## 修复主线

### 1. server 模型注册和部署配置

server 侧的问题本质是 `Provider Registry（供应商注册表）` 和部署环境没有完全对齐：

- `DeepSeek` 模型名仍使用旧的 `deepseek-chat/deepseek-reasoner`。
- 部署 workflow 没有显式传递 `DEEPSEEK_API_KEY`。
- runtime 模型列表虽然已经引入 registry，但默认 provider/model 仍有硬编码痕迹。
- 旧的 `LLM_PROXY_MODE` 描述和变量会误导排障。

本轮修复后：

- `DeepSeek` 平台模型统一为 `deepseek-v4-flash` 和 `deepseek-v4-pro`。
- 默认模型改为 `deepseek-v4-flash`，默认不进入推理模型路径。
- `.github/workflows/deploy-server.yml` 补齐 `DEEPSEEK_API_KEY` 的校验和运行时注入。
- `/api/v1/runtime/models` 根据实际可用 provider 动态选择默认 provider/model。
- server README 和 runtime 相关描述清理旧 `mock/upstream/LLM_PROXY_MODE` 概念。
- provider HTTP 错误增加关键字段透传，便于从 client 看到上游失败原因。

对应提交：

- `c110acf 修正 server 模型注册和部署配置`

### 2. core 工作区数据契约和素材一致性

core 侧集中处理两个事实源问题：

- `Project` 名称缺少可修改的 API 契约，client 只能展示创建时的静态名字。
- 素材和 clip 缺少足够强的数据一致性约束，重复上传、重复切分、重试失败和删除恢复都容易污染结果。

本轮修复后：

- 新增 `PATCH /api/v1/projects/{project_id}`，支持 project rename。
- `store` 持久化 title 变更，并发出 `project.updated` event。
- 自动命名逻辑改为更稳定的 deterministic heuristic（确定性启发式）。
- asset 导入基于 `fingerprint/source_path` 做防重。
- deleted 且已完成处理的 asset 重新加入时走 restore，不重复切分和向量化。
- failed asset 重新加入时复用原 asset 并触发 retry。
- clip 写入前做规范化去重，避免同一原始素材路径和时间范围重复进入结果集。
- soft delete/restore 先同步云端向量状态，失败时返回明确错误，避免本地显示删除成功但云端仍参与召回。
- asset retry 改成 staged retry（暂存式重试），失败时不破坏旧的可用 clips。
- chat failed task 写入稳定 `error` 字段，避免只依赖 WebSocket 的 `error.occurred`。

对应提交：

- `695cdb5 完善 core 工作区数据契约和素材一致性`

### 3. client 模型选择、Workspace 体验和错误可见性

client 侧主要修的是“显示状态与真实系统状态不一致”：

- Platform provider/model 下拉框仍有本地 mock fallback。
- 重新打开 Workspace 后，本地媒体 URL 没有根据持久化 `source_path` 恢复。
- WebSocket 断开时，用户看不到原因，active task 也缺少 polling fallback。
- server/provider 的嵌套错误没有完整显示。

本轮修复后：

- Platform 模型列表以 server catalog 为事实源。
- catalog 加载失败时不再伪造可用模型。
- BYOK 本地 DeepSeek 模型同步为 `deepseek-v4-flash/deepseek-v4-pro`。
- Workspace 加载后按 `asset.source_path` 重新注册本地媒体 URL。
- media registry、thumbnail、clip 选择逻辑统一改为优先使用 `asset.id`，避免重名素材互相覆盖。
- 源文件缺失时显示明确提示，并提供重新上传/重新定位入口。
- Workspace 顶部展示 WebSocket 状态。
- WebSocket 断开时对 active task 进行 HTTP polling fallback。
- chat 错误 banner 展示 `server_error/upstream_status/upstream_body_excerpt` 等关键细节。
- Launchpad 和 Workspace 支持 project inline rename。
- 素材支持删除、恢复、失败重试入口。

对应提交：

- `c9e9947 完善 client 工作区模型选择和媒体体验`

### 4. 文档和任务状态

为了让后续排查有上下文，本轮也补充了 task 和 diary：

- 更新 `docs/tasks/2026-05-05_registry_driven_model_routing_full_chain_plan.md`。
- 新增 `docs/tasks/2026-05-05_workspace_runtime_deploy_media_chat_issue_audit.md`。
- 新增 `docs/develop_diary/2026-05-05_server_deploy_secrets_and_model_catalog_audit_journal.md`。

对应提交：

- `e4ce38b 记录 Workspace runtime 问题审计和实施状态`

## 验证结果

用户在本地手动执行并确认通过：

```bash
source core/venv/bin/activate && PYTHONPATH=.:core pytest core/tests
npm --prefix client run typecheck
source server/venv/bin/activate && pytest server/tests
git diff --check
```

结果：

- `core/tests`: 38 passed，1 warning。
- `client typecheck`: passed。
- `server/tests`: 61 passed。
- `git diff --check`: passed。

## 提交与推送

本轮按职责拆分为四个提交，并已推送到 `origin/main`：

- `c110acf 修正 server 模型注册和部署配置`
- `695cdb5 完善 core 工作区数据契约和素材一致性`
- `c9e9947 完善 client 工作区模型选择和媒体体验`
- `e4ce38b 记录 Workspace runtime 问题审计和实施状态`

推送结果：

```text
7b0836e..e4ce38b main -> main
```

## 留在工作区的内容

按用户要求，和 UI 设计相关的改动没有纳入本轮提交，也没有在本文展开：

- `.gitignore`
- `client/src/App.tsx`
- `client/src/components/chat/`
- `client/src/ui_design/`

这些内容需要后续单独确认是否提交、拆分到独立分支，或作为 UI 设计实验继续保留。

## 后续关注点

1. 云端部署后，需要重新确认 `GET /api/v1/runtime/models` 返回的 provider/model 与部署 secrets 一致。
2. 真机登录失败如果再次出现，应优先区分网络/TLS/DNS 问题和 server API 问题。
3. Workspace 媒体恢复依赖本地 `source_path` 仍可访问，跨机器或文件移动场景仍需要更完整的重新定位流程。
4. clip 去重和向量状态同步已经收敛，但仍建议增加一轮带真实视频文件的端到端回归。
