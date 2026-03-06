# EntroCut 当前进度与任务拆分总览（2026-03-06）

## 1. 当前开发进度（Reality Check）

### 1.1 端到端主链路状态

| 链路 | 当前状态 | 说明 |
| --- | --- | --- |
| `Launchpad -> Workspace` 页面切换 | 已打通（MVP Shell） | `activeWorkspaceId` 驱动切换，未引入 `router（路由）`。 |
| 情况1：只上传视频 | 已打通（最小闭环） | 能创建项目、触发 `core ingest`、再触发 `server index`。 |
| 情况2：只输入提示词 | 已打通（最小闭环） | 能创建空项目并调用 `server chat`，会附带“先上传素材”的系统提示。 |
| 情况3：上传视频+提示词 | 已打通（最小闭环） | `pendingPrompt` 会等待素材处理完成后自动发送。 |
| 工作台 `Assets` 上传入口 | 已打通（最小闭环） | 支持点击上传与拖拽，统一走 `workspace store action`。 |

结论：主流程已从 `mock（假数据）` 迁移到真实接口调用，但整体仍处于 `Shell（壳层）` 阶段，核心能力是“流程正确”，不是“能力完整”。

### 1.2 各子系统现状

1. `client（前端）`
   1. `Zustand Store（状态管理）` 边界基本正确：页面主要负责触发动作与展示状态。
   2. `Launchpad/Workspace` 双 Store 已成型，三种启动情况逻辑已落地。
   3. `Electron Bridge（桥接）` 仅实现目录选择；不可用时回退到浏览器文件选择。
   4. 明显缺口：`electron:dev` 仍是 `TODO`，本地开发默认在浏览器环境运行，导致桥接能力不可稳定验证。
2. `core（本地服务）`
   1. 已提供 `projects/create/import/upload/get/ingest` 最小接口。
   2. 目前为内存态数据（进程重启即丢），且 `ingest` 是规则生成的假切片，不是实际视频处理管线。
   3. `search/render` 仍是 `501 NOT_IMPLEMENTED`。
3. `server（云端服务）`
   1. 已提供 `index/upsert-clips` 与 `chat` 最小接口。
   2. 目前为内存态索引、规则回复，不含真实 `LLM（大模型）`、`Vector DB（向量库）`、`Auth（鉴权）`。
4. `contract（契约）`
   1. 文档中目标契约（`EntroVideoProject`、结构化 `ops`、统一错误包）与实际返回结构存在偏差。
   2. 当前实现可跑通页面，但尚未达到“可冻结、可跨团队稳定协作”的契约成熟度。
5. `quality（质量保障）`
   1. 当前仓库几乎无自动化测试。
   2. 无统一 `CI（持续集成）` 校验门禁。

---

## 2. 逻辑缺失分类

## 2.1 第一类：全局性缺失（牵一发而动全身，需主工程师先搭）

### G1. 契约基线冻结（Contract Baseline Freeze）

- 为什么是全局：`client/core/server` 的输入输出都依赖它，不先冻结会导致并行开发互相打架。
- 当前缺口：
  - `chat` 响应的 `ops` 还是 `string[]`，未结构化。
  - 错误体未统一为 `ErrorEnvelope（错误包络）`。
  - `project/patch` 语义未按文档落地。
- 主工程师先交付：
  1. `v1` 冻结版 `schema`（`TypeScript + Pydantic` 同构）。
  2. 字段 `required/optional/nullable` 一览表。
  3. 版本演进规则（`major/minor`）。

### G2. 全链路状态机与任务编排（Workflow Orchestration）

- 为什么是全局：启动台、工作台、后端异步任务的状态必须一致，否则 UI 会乱跳或重复触发。
- 当前缺口：
  - 前端已有状态变量，但未形成明确 `state machine（状态机）` 契约。
  - `core ingest` 和 `server index/chat` 仍是串行直接调用，缺少任务级 `idempotency（幂等）` 与重试语义。
- 主工程师先交付：
  1. 统一状态机图（状态、事件、转移、失败分支）。
  2. `job model（任务模型）`：`job_id/status/progress/retryable`。
  3. 失败恢复策略：刷新后如何恢复处理中项目。

### G3. 项目与素材持久化模型（Project Persistence Model）

- 为什么是全局：不持久化就无法做稳定回归、历史项目复现、多人并行调试。
- 当前缺口：
  - `core/server` 都是内存态，重启丢数据。
  - 上传文件未进入规范化资产存储（仅记录文件名或路径）。
- 主工程师先交付：
  1. 最小持久化方案（`SQLite/Postgres` 二选一先定）。
  2. 资产索引模型（`project_id -> assets -> clips`）。
  3. 媒体生命周期规则（导入、追加、去重、删除、重建索引）。

### G4. 统一错误语义 + 可观测性（Observability）

- 为什么是全局：没有统一错误码和链路追踪，外包任务出现问题无法快速定位。
- 当前缺口：
  - 多端错误结构不一致。
  - 缺少 `request_id` 贯通、结构化日志、关键指标。
- 主工程师先交付：
  1. 错误码字典（`core/server/client` 分域且不重名）。
  2. 全链路 `request_id/session_id/project_id` 透传规范。
  3. 最小日志字段规范与采集策略。

### G5. 运行时矩阵与本地联调框架（Runtime Matrix）

- 为什么是全局：当前浏览器开发模式与 Electron 模式行为不一致，桥接能力无法稳定复现。
- 当前缺口：
  - `client` 的 `electron:dev` 未接通。
  - 联调脚本虽可启动三端，但未覆盖 Electron 通路验证。
- 主工程师先交付：
  1. 标准开发模式定义：`web-dev`、`electron-dev`、`smoke-test`。
  2. 一键联调脚本与健康检查规范。
  3. `bridge unavailable` 的标准降级与提示策略。

### G6. 质量门禁框架（Testing + CI Gate）

- 为什么是全局：没有门禁就无法放心并行外包，回归成本会指数上升。
- 当前缺口：缺少 Store 单测、API 合同测试、E2E 冒烟、CI 流程。
- 主工程师先交付：
  1. 测试分层策略（`unit/integration/e2e/contract`）。
  2. 必过清单（最小 gate）。
  3. CI 流水线初版（至少 `lint/typecheck/test/smoke`）。

---

## 2.2 第二类：可拆分独立任务（可并行外包）

> 说明：以下任务默认在 G1-G6 框架确定后并行推进。每个任务都可以独立分配给工程师，不改全局决策即可落地。

| ID | 模块 | 独立任务 | 依赖 | 交付标准（DoD） |
| --- | --- | --- | --- | --- |
| T1 | `client` | `electron:dev` 启动链路接通 | G5 | 一条命令启动 Electron + Vite，`showOpenDirectory` 可用。 |
| T2 | `client` | Launchpad 错误展示分级（可重试/不可重试） | G4 | 不同错误码显示明确行动建议。 |
| T3 | `client` | Workspace 处理中状态组件化 | G2 | `media_processing/indexing/chat_thinking` UI 一致。 |
| T4 | `client` | Store 单测（启动台三种情况） | G6 | 覆盖成功/失败/取消/桥接缺失分支。 |
| T5 | `client` | Store 单测（工作台上传与排队提示词） | G6 | 覆盖 `pendingPrompt` 队列行为。 |
| T6 | `core` | `POST /api/v1/search` 最小实现 | G1/G3 | 可按 `project_id+query` 返回稳定结果，非 `501`。 |
| T7 | `core` | `POST /api/v1/render` 最小实现 | G1/G3 | 返回可用 `preview_id/stream_url` 或明确异步任务状态。 |
| T8 | `core` | 上传素材去重与校验策略 | G3/G4 | 重复文件可识别；错误码准确。 |
| T9 | `core` | ingest 进度上报接口 | G2/G4 | 返回 `job_id + progress`，前端可轮询。 |
| T10 | `core` | 项目持久化存储适配器 | G3 | 重启后项目、素材、切片仍可读取。 |
| T11 | `server` | `chat` 输出升级为结构化 `ops` | G1 | 返回对象化 `ops`，通过契约校验。 |
| T12 | `server` | `ASK_USER_CLARIFICATION` 增补澄清字段 | G1 | 响应含明确追问文本与下一步建议。 |
| T13 | `server` | `index/upsert` 失败重试与部分失败语义 | G2/G4 | `indexed/failed` 可解释且可重试。 |
| T14 | `server` | 最小 `Vector Adapter（向量适配器）` 抽象层 | G1/G3 | 内存实现与真实实现可切换。 |
| T15 | `server` | `chat` 合同测试 | G1/G6 | 对 `decision_type` 三分支做 schema 断言。 |
| T16 | `shared` | 契约类型包（共享 schema） | G1 | `client/core/server` 共用同一份定义与版本号。 |
| T17 | `devops` | 冒烟脚本（含三种启动场景） | G5/G6 | 自动跑完 3 种场景并输出结果。 |
| T18 | `devops` | 统一日志落盘与轮转策略 | G4 | 三端日志字段统一，便于排障。 |
| T19 | `docs` | API 文档与实现对齐巡检 | G1 | 文档字段与实际返回一致，无关键漂移。 |
| T20 | `qa` | 端到端手测清单固化 | G6 | 每个版本可复用同一 checklist 回归。 |

---

## 3. 主工程师先搭框架（先手动作）

## 3.1 先搭什么（必须先完成）

1. 冻结 `Contract v1`（G1）。
2. 冻结启动到处理完成的 `State Machine`（G2）。
3. 冻结持久化与任务模型（G3）。
4. 冻结错误码与日志规范（G4）。
5. 冻结开发/联调/测试运行矩阵（G5 + G6）。

## 3.2 搭完后的并行批次建议

1. 批次A（平台基础）：`T1 + T10 + T16 + T17`  
2. 批次B（能力补齐）：`T6 + T7 + T11 + T14`  
3. 批次C（质量与体验）：`T2 + T3 + T4 + T5 + T15 + T20`  
4. 批次D（稳定性）：`T8 + T9 + T12 + T13 + T18 + T19`  

这样拆分后，不同工程师可以在低耦合前提下并行推进，主工程师只需守住 5 个全局基线即可。

---

## 4. 风险提示（按优先级）

1. 最大风险：契约未冻结就并行开发，会出现“前后端都对，但对不上”的假完成。
2. 第二风险：仍以内存态数据推进，会在联调阶段频繁出现“偶现不可复现”。
3. 第三风险：缺少自动化门禁，外包并行后回归成本会显著增加。

---

## 5. 建议的下一步（非编码）

1. 召开一次 `Contract Freeze Review（契约冻结评审）`，把 G1 的阻塞问题当天定稿。
2. 由主工程师发布 `Architecture Decision Record（架构决策记录）`：G2/G3/G4 一次性定版。
3. 以本文 `T1-T20` 建立任务看板，按批次A先派工。

