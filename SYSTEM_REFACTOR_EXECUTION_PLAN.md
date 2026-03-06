# EntroCut 系统清理与骨架重构推进思路

## 1. 目标

本轮工作的目标不是把所有功能一次性做完，而是按以下优先级推进：

1. 清理与设计文档冲突的错误代码和错误职责边界。
2. 先把 `Client / Core / Server` 三端骨架搭稳，保证主链路、事件模型、接口边界、状态流向正确。
3. 能被独立 `mock` 替代且不影响主骨架稳定性的能力，一律先用 `mock` 占位，不提前进入细节实现。
4. 输出完整 `Todo` 拆分表，为后续多工程师并行开发做准备。

本轮唯一 `source of truth（单一事实源）`：

1. `EntroCut_architecture.md`
2. `EntroCut_algorithm.md`
3. `EntroCut_launchpad_design.md`
4. `EntroCut_user_senerio.md`

## 2. 当前判断

当前仓库不是“完全无价值”，但存在明显的架构偏移：

1. `Client` 直接编排 `Core + Server`，而不是只面向 `Core`。
2. `Core` 没有成为“本地大脑”，缺失 `WebSocket / Agent orchestration / tool execution / event stream` 主体能力。
3. `Server` 承担了过多伪业务逻辑，没有收敛为 `Auth + Proxy + Retrieval gateway`。
4. 一部分接口虽然可运行，但语义是错的；这种代码比空壳更危险，因为会误导后续开发。

因此，本轮应采取：

1. 保留：`UI prototype（界面原型）`、`Electron shell（桌面壳层）`、少量稳定类型和页面结构。
2. 清理：职责错位的运行链路、伪算法实现、伪闭环接口、与设计文档冲突的旧文档和旧状态机。
3. 重建：三端骨架、主事件流、项目状态模型、接口契约外壳、`mock boundary（mock 边界）`。

## 3. 任务一：彻底扫描和清理错误代码

### 3.1 清理标准

满足以下任一条件的代码，应视为“错误代码”：

1. 与设计文档定义的职责边界相冲突。
2. 接口名正确但行为语义错误。
3. 暂时无法复用且会误导后续实现方向。
4. 把应当在 `Core` 的编排逻辑错误地放在 `Client` 或 `Server`。
5. 将未来应为 `streaming / event-driven（流式/事件驱动）` 的链路，硬编码成同步 `HTTP` 假流程。

### 3.2 第一批必须清理的错误点

1. `client -> server` 的直接业务调用链。
2. `Zustand store` 中混合了页面状态、跨端编排、API 编排、流程状态机的实现。
3. `Core` 中伪装成真实能力的 `ingest/search/render` 假实现。
4. `Server` 中不应存在的本地决策逻辑和伪索引逻辑。
5. 与上述错误实现绑定的旧文档、旧脚本、旧状态字段。

### 3.3 清理原则

1. 不删除 UI 视觉层。
2. 不删除 Electron 启动壳。
3. 不追求“文件最少”，追求“边界最清晰”。
4. 清理优先于补丁修修补补。
5. 每次清理后都要留下能继续开发的稳定骨架，而不是半废状态。

## 4. 任务二：主工程师负责搭系统骨架

### 4.1 骨架优先级

我作为主工程师，这一轮只做“全局性、牵一发而动全身”的基础层，不先陷入可独立外包的小功能。

优先搭建以下骨架：

1. 三端职责边界。
2. 主调用链和事件回流链。
3. 项目生命周期状态机。
4. `WebSocket event schema（事件契约）`。
5. `Core` 内部 `service / tool / gateway / repository` 分层。
6. `Server` 的 `auth / llm proxy / embedding proxy / vector proxy` 分层。
7. `Client` 的 `UI state / transport state / project state` 分层。

### 4.2 目标中的正确主链路

#### Launchpad

1. `Client` 捕获用户输入、拖拽目录、系统文件选择。
2. `Client` 只调用 `Core`。
3. `Core` 创建项目、扫描本地目录、写入本地项目元数据。
4. `Core` 触发 `Segmentation / Frame extraction / Embedding / Index sync` 流程。
5. `Core` 通过 `WebSocket` 持续向 `Client` 推送项目状态。
6. `Server` 只承担鉴权、中转、云端检索和模型代理。

#### Workspace

1. `Client` 与 `Core` 建立 `WebSocket` 会话。
2. 用户输入 `Prompt` 后先进入 `Core Agent`。
3. `Core` 决定是否调用 `Server` 的 `LLM`、`Embedding`、`Retrieval`。
4. `Core` 执行本地工具链，并回写本地项目状态。
5. `Core` 通过事件流把 `chat / operation / notification / project_patch / media_progress` 推回 `Client`。

### 4.3 三端最小骨架定义

#### Client Skeleton

1. 页面继续保留 `LaunchpadPage` 与 `WorkspacePage`。
2. `store` 只保留“状态投影”职责，不承担业务编排。
3. 新增 `core transport layer（到 Core 的传输层）`，统一管理：
   1. `REST` 初始化请求
   2. `WebSocket` 会话连接
   3. 事件订阅和断线重连
4. 页面只触发动作，页面内不直接写业务流程。

#### Core Skeleton

1. `FastAPI app` 只保留明确的入口层。
2. 增加 `WebSocket hub`。
3. 增加 `ProjectService`。
4. 增加 `WorkflowService`：
   1. `launch workflow`
   2. `ingest workflow`
   3. `chat workflow`
   4. `render workflow`
5. 增加 `ToolRegistry`：
   1. `segmentation tool`
   2. `frame extraction tool`
   3. `render tool`
   4. `project patch tool`
6. 增加 `ServerGateway`：
   1. `embedding proxy`
   2. `llm proxy`
   3. `vector search proxy`
7. 所有重实现可先 `mock`，但接口必须先稳定。

#### Server Skeleton

1. `FastAPI app`
2. `JWT auth middleware`
3. `LLMProxyService`
4. `EmbeddingProxyService`
5. `VectorSearchService`
6. `Usage/QuotaService`
7. 所有第三方外部依赖先做 `adapter interface（适配器接口）`，先留 `mock adapter`

## 5. 本轮明确不做的事情

### 5.1 不做

1. 不追求真实 `DashVector` 完整接入。
2. 不追求真实 `Qwen3-VL-Embedding` 完整接入。
3. 不追求真实 `PySceneDetect + FFmpeg` 的生产级算法效果。
4. 不做复杂时间线编辑器。
5. 不做多用户协作。
6. 不做跨设备同步闭环。

### 5.2 替代方案

以下能力允许先用 `mock`：

1. `embedding response`
2. `vector search result`
3. `llm plan result`
4. `render preview url`
5. `segment result`
6. `frame extraction result`

前提只有一个：`mock` 必须挂在稳定接口后面，而不是把假逻辑散落到 UI 和 Store 里。

## 6. 建议的实施阶段

| 阶段 | 目标 | 输出 | 是否允许 mock |
| --- | --- | --- | --- |
| Phase 0 | 统一设计基线与清理范围 | 文档、删除清单、保留清单 | 否 |
| Phase 1 | 清理错误调用链 | `Client -> Core` 单入口 | 否 |
| Phase 2 | Core 骨架落地 | `REST + WebSocket + workflow shell` | 是 |
| Phase 3 | Server 骨架落地 | `auth + proxy shell + adapter interface` | 是 |
| Phase 4 | Launchpad 主链路打通 | 创建项目、导入目录、状态推送 | 是 |
| Phase 5 | Workspace 主链路打通 | 聊天、状态事件、素材处理中约束 | 是 |
| Phase 6 | 替换 mock 为真实能力 | 分批接入算法和云端能力 | 否 |

## 7. 细分 Todo 总表

| ID | 优先级 | 任务 | 类型 | 依赖 | 是否可 mock | 负责人建议 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | P0 | 盘点并删除 `client -> server` 直连业务调用 | 全局骨架 | 无 | 否 | 主工程师 |
| T02 | P0 | 重构 `Zustand store`，只保留状态投影和事件消费 | 全局骨架 | T01 | 否 | 主工程师 |
| T03 | P0 | 设计并落地 `Core REST API` 最小入口集合 | 全局骨架 | T01 | 否 | 主工程师 |
| T04 | P0 | 设计并落地 `Core WebSocket event schema` | 全局骨架 | T03 | 否 | 主工程师 |
| T05 | P0 | 设计 `Project lifecycle state machine` | 全局骨架 | T03 | 否 | 主工程师 |
| T06 | P0 | 重构 `core/` 目录分层：`api / services / workflows / tools / gateways / repositories` | 全局骨架 | T03 | 否 | 主工程师 |
| T07 | P0 | 重构 `server/` 目录分层：`api / auth / proxies / adapters / repositories` | 全局骨架 | T03 | 否 | 主工程师 |
| T08 | P1 | 建立 `Launchpad workflow shell` | 主链路 | T04 T05 T06 | 是 | 主工程师 |
| T09 | P1 | 建立 `Workspace chat workflow shell` | 主链路 | T04 T05 T06 T07 | 是 | 主工程师 |
| T10 | P1 | 统一 `ErrorEnvelope / request_id / event payload` 契约 | 全局骨架 | T03 T04 T07 | 否 | 主工程师 |
| T11 | P1 | 建立 `ServerGateway` 抽象接口 | 基础设施 | T06 | 否 | 可外包 |
| T12 | P1 | 建立 `ToolRegistry` 与 `Tool execution context` | 基础设施 | T06 | 否 | 可外包 |
| T13 | P1 | 实现 `segment tool mock` | 独立能力 | T12 | 是 | 可外包 |
| T14 | P1 | 实现 `frame extraction tool mock` | 独立能力 | T12 | 是 | 可外包 |
| T15 | P1 | 实现 `render tool mock` | 独立能力 | T12 | 是 | 可外包 |
| T16 | P1 | 实现 `embedding proxy mock adapter` | 独立能力 | T07 T11 | 是 | 可外包 |
| T17 | P1 | 实现 `vector search mock adapter` | 独立能力 | T07 T11 | 是 | 可外包 |
| T18 | P1 | 实现 `llm plan mock adapter` | 独立能力 | T07 T11 | 是 | 可外包 |
| T19 | P2 | 接入真实 `PySceneDetect` | 算法实现 | T13 | 否 | 专项工程师 |
| T20 | P2 | 接入真实 `FFmpeg` 抽帧 | 算法实现 | T14 | 否 | 专项工程师 |
| T21 | P2 | 接入真实 `FFmpeg render/export` | 算法实现 | T15 | 否 | 专项工程师 |
| T22 | P2 | 接入真实 `Qwen3-VL-Embedding` 代理 | 云端实现 | T16 | 否 | 专项工程师 |
| T23 | P2 | 接入真实 `DashVector search` | 云端实现 | T17 | 否 | 专项工程师 |
| T24 | P2 | 接入真实 `LLM planning` | 云端实现 | T18 | 否 | 专项工程师 |
| T25 | P2 | 梳理并归档与新架构冲突的旧文档 | 文档治理 | T01 T03 T04 | 否 | 可外包 |
| T26 | P2 | 建立 `smoke test`：启动台导入到工作台事件流 | 验证 | T08 T09 T10 | 是 | 可外包 |
| T27 | P2 | 建立 `directory ingest progress` 的 UI 事件映射 | UI 接线 | T04 T08 | 是 | 可外包 |
| T28 | P2 | 建立 `workspace chat event` 的 UI 事件映射 | UI 接线 | T04 T09 | 是 | 可外包 |

## 8. 我作为主工程师的执行顺序

本轮我会先抓以下顺序，不先分散到细枝末节：

1. 清理错误职责和错误调用链。
2. 把 `Client -> Core` 单入口确定下来。
3. 把 `Core` 的 `REST + WebSocket + state machine + workflow shell` 搭起来。
4. 把 `Server` 的 `proxy/gateway skeleton` 搭起来。
5. 再把 `Launchpad -> Workspace` 主链路做成稳定骨架。

只有在这条骨架稳定后，才把 `mock` 能力分发给其他工程师替换成真实实现。

## 9. 下一步落地原则

下一轮真正开始编码时，必须遵守：

1. 先删错的，再补对的。
2. 先搭边界，再填实现。
3. 页面组件不写脏活，业务编排不放到 UI。
4. 能 `mock` 的独立能力，一律先 `mock`，不要抢跑。
5. 每一层都只对下一层暴露稳定契约，不泄露实现细节。

