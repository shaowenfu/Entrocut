# Phase 4/5 工程师任务分发清单

## 1. 当前基线

截至当前版本，以下骨架已经由主工程师搭好并通过最小全链路验证：

1. `Client -> Core -> Server` 单入口主链路已经收口，`Client` 不再直接调用 `Server` 业务 API。
2. `Core skeleton` 已具备：
   1. `REST entry`
   2. `WebSocket hub`
   3. `workflow shell`
   4. `tool registry`
   5. `server gateway shell`
3. `Server skeleton` 已具备：
   1. `proxy service`
   2. `adapter interface`
   3. `mock provider`
4. `Client` 已具备：
   1. `Launchpad / Workspace UI prototype`
   2. `Core event transport`
   3. `Workspace event stream` 接线骨架
5. 一次性三端冒烟脚本已通过：

```bash
bash scripts/phase45_smoke_test.sh
```

当前冒烟验证覆盖：

1. `Client` dev server 可启动
2. `Core` 可启动
3. `Server` 可启动
4. `upload -> ingest -> index -> chat`
5. `WebSocket events`：
   1. `session.ready`
   2. `media.processing.progress`
   3. `media.processing.completed`
   4. `workspace.chat.received`
   5. `workspace.chat.ready`
   6. `workspace.patch.ready`

## 2. 总原则

所有工程师必须遵守以下边界：

1. 页面组件只负责 `trigger（触发）` 和 `render（展示）`，不要把业务编排写回页面。
2. `Client` 不允许新增直接到 `Server` 的业务调用。
3. `Core` 是唯一的本地业务编排中心。
4. `Server` 只做 `auth / proxy / retrieval / quota`，不要把本地媒体处理逻辑塞进 `Server`。
5. 没有主工程师批准，不要改：
   1. `WebSocket event schema`
   2. `Client -> Core -> Server` 主链路
   3. 根目录的四份设计文档
6. 可独立 `mock` 的逻辑，允许先保留 `mock` 接口并逐步替换真实实现。

## 3. 主工程师保留项

以下内容不外包，继续由主工程师持有：

1. 三端职责边界
2. `REST/WebSocket` 契约
3. `workflow/state machine`
4. `core/server` 入口接线
5. `store` 顶层职责收口
6. 跨端 `ErrorEnvelope / request_id / event payload` 统一语义

## 4. 可并行分发任务总表

| 任务 ID | 负责人 | 任务主题 | 允许修改 | 禁止修改 | 依赖 | DoD |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | 工程师 A | `Core Segmentation + Frame Extraction` 真实现 | `core/app/tools/*`, `core/requirements.txt`, 必要 docs | `client/`, `server/`, `core/server.py` 主入口结构 | 已完成骨架 | 替换 `segment/extract_frames` mock，提供最小回归测试 |
| E2 | 工程师 B | `Core Render / Export` 真实现 | `core/app/tools/*`, `core/app/workflows/*`, 必要 docs | `client/`, `server/`, `WebSocket schema` | 已完成骨架 | `render_preview` 不再是纯 mock，可返回真实本地预览输出 |
| E3 | 工程师 C | `Server Embedding + DashVector Adapter` | `server/app/adapters/*`, `server/app/services/*`, `server/requirements.txt`, 必要 docs | `client/`, `core/`, `server/main.py` 主入口结构 | 已完成骨架 | `EmbeddingAdapter` 和 `VectorSearchAdapter` 可接真实服务并带 smoke |
| E4 | 工程师 D | `Server LLM Planning Adapter` | `server/app/adapters/*`, `server/app/services/*`, prompt docs | `client/`, `core/`, `WebSocket schema` | 已完成骨架 | `LLMProxyService` 可输出真实规划结果并满足现有返回契约 |
| E5 | 工程师 E | `Client Event-Driven UI Polish` | `client/src/store/*`, `client/src/services/*`, `client/src/pages/*` | `core/`, `server/`, 跨端契约字段名 | 已完成骨架 | `Launchpad/Workspace` 主要状态依赖事件流而非前端假状态 |
| E6 | 工程师 F | `QA / Smoke / E2E Automation` | `scripts/*`, 测试文档, 必要 CI 脚本 | 业务逻辑主文件 | 已完成冒烟样板 | 提供稳定的本地与 CI 冒烟测试矩阵 |

## 5. 逐人任务说明

### 工程师 A：Core 镜头切分与关键帧提取

你的任务是把 `Core` 的 `Segmentation（镜头切分）` 和 `Frame Extraction（关键帧提取）` 从 `mock tool` 替换为真实实现。

你的执行边界：

1. 允许修改：
   1. `core/app/tools/registry.py`
   2. `core/app/tools/mocks.py`
   3. `core/app/tools/` 下新增真实工具文件
   4. `core/requirements.txt`
   5. 必要的 `core/README.md` 或配套文档
2. 禁止修改：
   1. `client/`
   2. `server/`
   3. `core/server.py` 的路由结构
   4. `WebSocket event schema`

完成定义：

1. `segment` 工具能返回真实切分结果
2. `extract_frames` 工具能返回真实关键帧产物或产物引用
3. 不破坏现有 `phase45_smoke_test.sh`

### 工程师 B：Core 渲染与导出

你的任务是实现 `Core` 的 `Render / Export` 能力，让 `render_preview` 从占位逻辑进化为真实本地预览能力。

你的执行边界：

1. 允许修改：
   1. `core/app/tools/*`
   2. `core/app/workflows/*`
   3. 必要文档
2. 禁止修改：
   1. `client/`
   2. `server/`
   3. `core/server.py` 的接口路径和事件名

完成定义：

1. `render_preview` 有真实本地输出
2. 输出结果仍遵守现有 `Core` 契约
3. 工作台后续可直接接入，不需要再改字段

### 工程师 C：Server 向量化与检索适配器

你的任务是将 `Server` 侧的 `EmbeddingAdapter` 与 `VectorSearchAdapter` 从 `mock` 替换为真实云服务。

你的执行边界：

1. 允许修改：
   1. `server/app/adapters/*`
   2. `server/app/services/*`
   3. `server/requirements.txt`
   4. 必要说明文档
2. 禁止修改：
   1. `client/`
   2. `core/`
   3. `server/main.py` 对外路径

完成定义：

1. `embed_frame_sheet()` 可走真实云端向量化
2. `semantic_search()` 可走真实 `DashVector`
3. 保持 `mock` fallback，不阻塞整体开发

### 工程师 D：Server 规划型 LLM Adapter

你的任务是实现 `LLM planning`，让 `Server` 真正输出结构化剪辑规划，而不是目前的固定 mock 结果。

你的执行边界：

1. 允许修改：
   1. `server/app/adapters/*`
   2. `server/app/services/*`
   3. prompt 模板文档
2. 禁止修改：
   1. `client/`
   2. `core/`
   3. `ChatDecisionResponse` 的冻结字段名

完成定义：

1. 输出遵守现有 `ChatDecisionResponse` 契约
2. `reasoning_summary / ops / storyboard_scenes` 结构稳定
3. 支持无素材和有素材两类输入

### 工程师 E：Client 事件驱动接线收尾

你的任务是把 `Client` 侧剩余的假状态收敛掉，让 `Launchpad` 与 `Workspace` 主要依赖 `Core event stream` 驱动。

你的执行边界：

1. 允许修改：
   1. `client/src/store/*`
   2. `client/src/services/*`
   3. `client/src/pages/*`
2. 禁止修改：
   1. `core/`
   2. `server/`
   3. 跨端契约字段与事件名

完成定义：

1. 页面状态不再主要依赖前端手工拼接
2. 支持 `WebSocket reconnect`
3. 错误状态和 loading 状态不互相打架

### 工程师 F：QA 与自动化验证

你的任务是把当前的一次性冒烟脚本扩展成可持续运行的自动化验证体系。

你的执行边界：

1. 允许修改：
   1. `scripts/*`
   2. 测试文档
   3. CI 辅助脚本
2. 禁止修改：
   1. 业务实现主逻辑
   2. `client/core/server` 的运行时边界

完成定义：

1. 本地 smoke 稳定
2. 提供最小 `CI smoke matrix`
3. 能覆盖：
   1. 三端启动
   2. `upload -> ingest -> index -> chat`
   3. `WebSocket event` 基本链路

## 6. 当前推荐并行顺序

建议立即并行启动：

1. 工程师 A
2. 工程师 C
3. 工程师 D
4. 工程师 E
5. 工程师 F

工程师 B 可以在 A 的工具输出接口更稳定后跟进，但也可以先做 `render tool` 的独立实现外壳。

## 7. 提交要求

所有工程师在提交前必须完成：

1. 只修改自己边界内的文件
2. 不改跨端冻结契约
3. 提供最小验证命令
4. 在 PR 描述中明确：
   1. 修改范围
   2. 未覆盖风险
   3. 对主链路是否有影响

