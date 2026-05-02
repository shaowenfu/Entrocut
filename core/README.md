# EntroCut Core

`core/` 是 EntroCut 的本地 `FastAPI（服务框架）` 后端进程。它面向 `client/` 提供稳定的本地 `HTTP API（超文本传输接口）` 与 `WebSocket（双向事件通道）` 契约，负责项目状态、素材导入、`EditDraft（剪辑草案）`、`agent loop（智能体循环）`、预览与导出。

当前它不是一个只返回 `health check（健康检查）` 的空壳，也不是最终完整的视频剪辑引擎。更准确地说，它是：

`SQLite-backed local backend（基于 SQLite 的本地后端） + EditDraft 事实源 + planner-driven agent loop（规划驱动的智能体循环）承载层`

## 核心目录导航

```text
core/
├── server.py                         # FastAPI app 装配入口：CORS、request_id、异常 envelope、router 挂载
├── desktop_entry.py                  # Electron 打包后启动入口：读取 CORE_PORT 并运行 uvicorn
├── config.py                         # 运行时配置：Server 地址、模型名、超时、agent loop 最大轮次
├── schemas.py                        # Pydantic Schema（数据契约）：API、WS、EditDraft、Task、RenderPlan
├── store.py                          # 本地应用服务层：项目内存镜像、任务编排、事件广播、chat/import/export 队列
├── state.py                          # SQLite Repository（仓储）：projects、drafts、tasks、assets、auth session 持久化
├── storage.py                        # app data 路径解析：db/projects/logs 根目录与 SQLite 文件位置
├── manager.py                        # WorkspaceManager：项目工作目录、preview/export/temp/proxies 子目录管理
├── helpers.py                        # 纯辅助函数：ID、时间、草案构建、摘要、兼容数据转换
├── context.py                        # Planner Context（规划上下文）组装：goal/scope/media/capabilities/memory
├── agent.py                          # chat 主链：请求 planner、校验决策、执行 read/retrieve/inspect/patch/preview
├── retrieval.py                      # retrieve tool：调用 Server /v1/assets/retrieval 召回候选 clip
├── inspection.py                     # inspect tool：对候选 clip 做轻量结构化检查
├── patching.py                       # patch tool：应用 EditDraftPatch 到 shots/scenes
├── rendering.py                      # preview/export 渲染：RenderPlan -> ffmpeg 输出文件
├── ingestion.py                      # 媒体 ingest 辅助：SceneDetect 分段、ffmpeg 抽帧、Pillow 拼图
├── routers/
│   ├── __init__.py                   # 聚合 projects/auth/system routers
│   ├── system.py                     # /、/health、runtime capabilities、project events WebSocket
│   ├── projects.py                   # projects/workspace/assets:import/chat/export API
│   └── auth.py                       # core auth session mirror API
├── tests/
│   ├── test_context_engineering.py   # planner context 与 runtime state 相关回归
│   ├── test_ingestion.py             # ingest 链路基础测试
│   ├── test_mvp_closure_pipeline.py  # patch/render/export 最小闭环测试
│   ├── test_real_ingest_contract.py  # 真实媒体导入契约测试
│   └── test_server_toolchain_integration.py # server/toolchain 集成边界测试
├── scripts/
│   └── build_desktop_core.sh         # PyInstaller 构建桌面 core-dist
├── requirements.txt                  # Python 依赖清单
└── pyinstaller.spec                  # 桌面 core 打包配置
```

生成物说明：

- `core/dist/`、`core/build/` 是打包产物目录，不属于核心源码。
- `venv/` 是本地 `virtual environment（虚拟环境）`，不属于核心源码。
- 默认本地数据不写在源码目录，而写入系统 app data 目录；可用 `ENTROCUT_APP_DATA_ROOT` 覆盖。

## 当前职责边界

从第一性原理看，`core` 维护的事实不是“UI 上的故事板”，而是可执行的剪辑状态：

`Asset（素材） -> Clip（检索/分析片段） -> Shot（可编辑镜头） -> Scene（分组） -> EditDraft（剪辑草案）`

当前权威事实源是 `EditDraft`，其中：

- `assets` 描述导入素材和处理状态。
- `clips` 是 ingest 与 retrieval 的基础单元。
- `shots` 是真正可渲染、可编辑的最小单位。
- `scenes` 是 UI 和规划辅助分组，不是独立持久化事实源。
- `summary_state / media_summary / runtime_state / capabilities` 是从项目、草案、任务与运行时派生出来的状态面。

## 已落地能力

### 1. 本地项目与 WorkspaceSnapshot

`core` 支持创建项目、列出最近项目、读取 workspace snapshot（工作区快照）。`POST /api/v1/projects` 当前只创建空 `EditDraft`，可携带 `prompt` 初始化目标，但不会直接把 `payload.media` 变成素材或片段。

`WorkspaceSnapshot` 当前包含：

- `project`
- `edit_draft`
- `chat_turns`
- `summary_state`
- `media_summary`
- `runtime_state`
- `capabilities`
- `active_tasks / active_task`
- `preview_result / export_result`

`active_tasks` 是当前权威任务集合，`active_task` 只是兼容旧调用方的便利字段。

### 2. SQLite 本地持久化

`state.py` 当前使用 `SQLite（嵌入式关系数据库）` 保存核心状态：

- `projects`
- `edit_drafts`
- `chat_turns`
- `tasks`
- `project_runtime`
- `assets`
- `core_auth_session`

默认 app data layout（应用数据布局）由 `storage.py` 管理：

```text
app_data_root/
├── db/                               # entrocut.sqlite3
├── projects/                         # 每个项目的工作目录
└── logs/                             # 预留日志目录
```

每个项目的 workspace 由 `manager.py` 创建：

```text
projects/{project_id}/
├── thumbs/                           # 缩略图预留目录
├── preview/                          # preview 渲染产物
├── exports/                          # export 渲染产物
├── temp/                             # 临时文件
└── proxies/                          # proxy media 预留目录
```

### 3. 真实素材导入链路

真实媒体入口只有：

`POST /api/v1/projects/{project_id}/assets:import`

当前约束：

- 必须先通过 `POST /api/v1/auth/session` 同步本地 `access_token`，否则返回 `AUTH_SESSION_REQUIRED`。
- `media.files[*].path` 必须是本机可读的绝对文件路径。
- `folder_path` 不能直接 ingest；桌面端必须先扫描目录并展开成 `files[]`。
- 不存在路径、目录路径、空路径会稳定返回可分支处理的 `CoreApiError（核心接口错误）`。

导入后台任务会做：

1. 将新素材写入 `EditDraft.assets`，状态为 `pending`。
2. 用 `SceneDetect（场景检测）` 分段生成 `Clip`。
3. 用 `ffmpeg` 抽帧，并用 `Pillow` 拼接 2x2 图片。
4. 调用 `Server /v1/assets/vectorize` 写入向量索引。
5. 更新素材状态为 `ready`，并推送 `edit_draft.updated / asset.updated / task.updated / capabilities.updated` 等事件。

### 4. Chat 与 Agent Loop

`POST /api/v1/projects/{project_id}/chat` 当前不是普通聊天接口，而是一次围绕 `EditDraft` 收敛的工作流入口。

主链路是：

1. 写入 user turn。
2. 从当前 workspace 派生 `planner context packet（规划上下文包）`。
3. 调用 `Server /v1/chat/completions`，或在 `X-Routing-Mode: BYOK` 时调用用户自带的 OpenAI-compatible endpoint（兼容 OpenAI 接口）。
4. 要求 planner 返回严格 JSON 决策。
5. 根据 `capabilities` 校验 tool 是否允许执行。
6. 执行最小 tool loop：`read / retrieve / inspect / patch / preview`。
7. 将 `EditDraft`、`runtime_state`、assistant turn、task 状态回写并广播。

当前 tool 能力：

- `read`：读取当前草案摘要，降低基于旧状态决策的风险。
- `retrieve`：调用 Server 向量检索，根据 project filter 召回 clip。
- `inspect`：对候选 clip 做结构化检查与摘要。
- `patch`：通过 `EditDraftPatch` 写入 shots/scenes。
- `preview`：基于当前 `RenderPlan` 渲染预览产物并广播 `preview.completed`。

当前 `draft_strategy（草案策略）` 仍只有：

- `placeholder_first_cut`
- `no_change`

这说明 `agent loop` 已经是可运行闭环，但还不是最终的高质量精剪引擎。

### 5. Preview 与 Export

`rendering.py` 以 `EditDraft.shots` 构建 `RenderPlan`，然后用 `ffmpeg` 截取片段并 concat（拼接）成 mp4。

当前接口：

- `preview` 由 `agent.py` 的 `preview tool` 触发，输出到项目 `preview/`。
- `POST /api/v1/projects/{project_id}/export` 触发后台 render task，输出到项目 `exports/`。

重要约束：

- 没有 `shots` 时不能 export，会返回 `EDIT_DRAFT_REQUIRED`。
- 渲染依赖系统可执行的 `ffmpeg`。
- 如果源文件不存在，渲染层会用黑色视频片段兜底，这主要服务测试和最小闭环，不代表生产质量目标。

### 6. Auth Session Mirror

`core` 只保存 `access_token / user_id` 的本地镜像，用于调用 Server 侧能力：

- `POST /api/v1/auth/session`
- `DELETE /api/v1/auth/session`

当前原则：

- `core` 不保存 `refresh_token`。
- `core` 不直接持有平台 LLM 密钥。
- `BYOK（Bring Your Own Key，自带密钥）` 模式下，`X-BYOK-Key` 只从请求头进入当前 chat 调用，不写入 SQLite。

## API 与事件契约

### HTTP API

```text
GET    /                                           # 根信息与当前环境摘要
GET    /health                                     # 健康检查
GET    /api/v1/runtime/capabilities                # core 当前保留能力面
GET    /api/v1/projects                            # 最近项目列表
POST   /api/v1/projects                            # 创建项目与空 EditDraft
GET    /api/v1/projects/{project_id}               # 读取 WorkspaceSnapshot
POST   /api/v1/projects/{project_id}/assets:import # 导入本地媒体文件
POST   /api/v1/projects/{project_id}/chat          # 触发 planner-driven chat/agent loop
POST   /api/v1/projects/{project_id}/export        # 导出当前 EditDraft
POST   /api/v1/auth/session                        # 同步 client access_token 到 core
DELETE /api/v1/auth/session                        # 清除 core auth session
```

### WebSocket API

```text
WS /api/v1/projects/{project_id}/events
```

连接成功后会先推送一次 `workspace.snapshot`，之后按项目事件递增 `sequence`。

当前事件名包括：

- `workspace.snapshot`
- `task.updated`
- `edit_draft.updated`
- `asset.updated`
- `project.updated`
- `project.summary.updated`
- `capabilities.updated`
- `chat.turn.created`
- `agent.step.updated`
- `preview.completed`
- `export.completed`
- `error.occurred`

### 错误语义

`CoreApiError` 会被统一包装成：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message.",
    "details": {},
    "request_id": "..."
  }
}
```

这意味着调用方应基于 `error.code` 做分支，而不是解析自然语言 `message`。

## 运行方式

首次准备：

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

本地启动：

```bash
cd core
source venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

可选环境变量：

```bash
export ENTROCUT_APP_DATA_ROOT=/tmp/entrocut-core-data
export SERVER_BASE_URL=http://127.0.0.1:8001
export SERVER_CHAT_MODEL=entro-reasoning-v1
export SERVER_CHAT_TIMEOUT_SECONDS=30
export AGENT_LOOP_MAX_ITERATIONS=3
```

桌面打包入口：

```bash
cd core
source venv/bin/activate
pip install pyinstaller
bash scripts/build_desktop_core.sh
```

该脚本会基于 `pyinstaller.spec` 生成 `dist/core-dist`，供 `client/electron-builder.yml` 作为桌面资源打包。

## 测试

```bash
cd core
source venv/bin/activate
pytest
```

当前测试覆盖重点：

- `planner context（规划上下文）` 的结构化输出。
- ingest 入口和真实导入契约。
- `EditDraftPatch` 到 `RenderPlan` 再到 export 的最小闭环。
- Server/toolchain 集成边界。

## 代码阅读顺序

建议按职责从外到内阅读：

1. [server.py](./server.py) - app 装配、异常格式、router 挂载。
2. [routers/projects.py](./routers/projects.py) - client 可调用的项目主 API。
3. [store.py](./store.py) - 任务、事件、导入、chat、导出编排。
4. [schemas.py](./schemas.py) - 公开契约和内部模型边界。
5. [state.py](./state.py) - SQLite 持久化形状。
6. [context.py](./context.py) - planner 输入如何由 workspace 派生。
7. [agent.py](./agent.py) - planner 调用、tool gating、tool execution loop。
8. [patching.py](./patching.py) 与 [rendering.py](./rendering.py) - 草案修改与渲染闭环。
9. [ingestion.py](./ingestion.py) 与 [retrieval.py](./retrieval.py) - 媒体入库与检索外部依赖。

## 当前非目标

为保护契约与复杂度预算，当前 `core` 明确不做：

- 不实现完整传统多轨时间线编辑器。
- 不把 UI 派生的 storyboard 作为独立事实源。
- 不在 `core` 本地保存 `refresh_token` 或平台级 LLM 密钥。
- 不绕过 `planner` 直接在 `/chat` 中偷跑不可解释工具。
- 不在 `POST /api/v1/projects` 中隐式 ingest 媒体。
- 不让 `folder_path` 直接进入 ingest；目录扫描属于桌面端职责。
- 不承诺当前 `placeholder_first_cut` 是最终剪辑质量方案。
- 不把当前 `ffmpeg` 渲染参数视为最终生产级编码策略。

## 后续最值得推进的方向

- 收紧 `EditDraftPatch` 表达力，让 planner 能描述更多真实编辑操作，而不是只依赖 `insert_shot`。
- 为 `store.py` 中的事件归约与任务状态转换补更细的回归测试。
- 将 ingest 的失败恢复、重复素材处理、向量化批次重试做成可枚举状态。
- 明确 `Server` 侧 planner/retrieval/vectorize 契约版本，避免 core 与 server schema 漂移。
- 改善 preview/export 的 `ffmpeg` 参数、音频处理与产物 metadata。
