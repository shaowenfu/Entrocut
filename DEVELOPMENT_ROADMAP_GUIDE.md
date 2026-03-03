# EntroCut 开发路线指导（Roadmap Guide）

版本：`v1.0`  
适用范围：当前 `Monorepo（单仓）` 下 `client/core/server/docs`  
目标：以 `Feature Slice（功能切片）` 驱动，替换现有 `Mock（模拟）`，逐步落地 `Chat-to-Cut（对话生成剪辑）` 闭环。

---

## 1. 当前基线（Current Baseline）

## 1.1 已具备

1. `docs/` 文档体系已成型，核心边界、`Contract（契约）`、`API（接口）`、`Workflow（流程）` 已定义。
2. `client` 已有高保真 UI，可用于交互链路联调与视觉验收。
3. `core/server` 均已提供最小 `FastAPI` 壳层与健康检查接口。

## 1.2 关键缺口

1. `client` 仍以内嵌 `Mock` 数据和本地 `setTimeout` 驱动，不是后端真实回包。
2. `core/server` 的业务接口仍是 `501 NOT_IMPLEMENTED` 占位。
3. 前端显示模型与文档契约存在偏差（如 `ops` 结构、时间字段语义）。
4. 缺少 `E2E（端到端）` 回归测试与统一 `Error Semantics（错误语义）` 断言。

## 1.3 第一性原则（First Principles）

1. 先验证主闭环，再扩展能力：`chat -> contract -> render`。
2. 以契约为边界，不以实现细节驱动接口。
3. 一个切片只解决一类业务能力，避免跨切片并发改动。

---

## 2. 总体执行策略（Execution Strategy）

## 2.1 开发顺序（固定）

1. 定义功能边界与数据契约。
2. 实现 `core/server` 端点与最小可用逻辑。
3. 替换 `client` 对应区域 `mock`。
4. 通过该切片的 `E2E` 验收。

## 2.2 每个切片的统一 DoD（Definition of Done）

1. 文档先行：契约、错误码、输入输出样例更新完成。
2. 三端一致：`TypeScript Model`、`Pydantic Model`、运行时响应一致。
3. Mock 清理：目标功能路径不再依赖本地假数据。
4. 可验证：至少 1 条稳定可复现 `E2E` 用例通过。
5. 可观测：请求具备 `request_id/session_id/project_id/user_id` 追踪字段。

---

## 3. 切片路线（Feature Slices）

## Slice 0：Contract Baseline（契约基线冻结）

目标：

1. 冻结 `EntroVideoProject`、`ChatRequest`、`AgentDecision`、`Patch`、`ErrorEnvelope`。
2. 明确 `client` 视图数据与契约字段的映射规则。

产物：

1. `SLICE0_CONTRACT_REVIEW_CHECKLIST.md`
2. `docs/04_CONTRACTS.md`（必要时增补）
3. `docs/05_API_CORE_LOCAL.md`、`docs/06_API_SERVER_CLOUD.md`（对齐字段）

验收：

1. 无歧义字段（类型、单位、可空性、默认值明确）。
2. `decision_type` 分支行为可被前端无条件分流处理。

---

## Slice 1：Health & Session Bootstrap（健康状态与会话初始化）

目标：

1. `client` 顶栏 `core/server` 状态灯接入真实 `GET /health`。
2. 建立会话基础：`session_id` 生成、透传、展示。

后端最小实现：

1. `core /health` 返回标准结构。
2. `server /health` 返回标准结构。

前端替换：

1. 移除硬编码在线状态。
2. 启动时轮询健康状态（或一次探测 + 失败重试）。

E2E：

1. 模拟 `core` 不可用时，UI 状态正确退化并可恢复。

---

## Slice 2：Chat Decision Loop（对话决策闭环）

目标：

1. 打通 `POST /api/v1/chat` 单一入口。
2. 前端不再使用 `setTimeout` 模拟 AI 决策。

后端最小实现：

1. 支持 `decision_type=UPDATE_PROJECT_CONTRACT`。
2. 返回合法 `reasoning_summary` 与结构化 `ops`。

前端替换：

1. `Copilot` 发送真实请求并渲染真实响应。
2. `isThinking` 状态完全由请求生命周期控制。

E2E：

1. 输入提示词后，对话区出现用户消息、决策卡、错误提示三种路径均可验证。

---

## Slice 3：Render Preview（预览渲染）

目标：

1. 打通 `POST /api/v1/render`。
2. 右侧舞台由占位层切为真实 `preview` 源。

后端最小实现：

1. `core` 接收 `project` 契约并返回 `preview_id + stream_url + duration_ms`。

前端替换：

1. 用真实 `duration_ms` 驱动进度条总时长。
2. 渲染失败时走统一错误卡片，而非静默失败。

E2E：

1. 首次生成后可播放预览，微调后可触发重渲染。

---

## Slice 4：Ingest & Index（素材摄入与向量入库）

目标：

1. 打通 `core /api/v1/ingest`。
2. 打通 `server /api/v1/index/upsert-clips`。

后端最小实现：

1. `core` 返回 `asset + clips + stats`。
2. `server` 支持批量 `upsert`，按 `user_id` 入索引。

前端替换：

1. 左栏 `Assets/Clips` 改为真实数据源。
2. 增加 `Processing -> Ready -> Failed` 状态标记。

E2E：

1. 导入素材后，左栏可见真实切片数量和处理时长。

---

## Slice 5：Refine via Patch（补丁式微调）

目标：

1. 支持 `decision_type=APPLY_PATCH_ONLY`。
2. `Storyboard` 局部更新，不重建全量状态。

后端最小实现：

1. 输出标准 `patch`/`ops`，支持最小 `replace` 操作。

前端替换：

1. 应用 `patch` 后触发 `Patch Highlight（补丁高亮）`。
2. 决策卡 `ops` 与分镜变更一一可追踪。

E2E：

1. “替换第 N 镜头”路径可稳定重复。

---

## Slice 6：Export Lock（导出与编辑锁）

目标：

1. 打通 `core /api/v1/export` + `GET /api/v1/jobs/{job_id}`。
2. 导出期间全局禁用编辑入口。

后端最小实现：

1. 提供任务状态机：`queued/running/succeeded/failed`。

前端替换：

1. 导出按钮联动状态、错误提示、恢复操作。

E2E：

1. 导出中发送 chat/编辑动作被拒绝，导出完成后解锁。

---

## Slice 7：Hardening（稳定性加固）

目标：

1. 建立基础测试矩阵与关键指标监控。
2. 固化错误语义与重试策略。

内容：

1. `Contract Compatibility Check（契约兼容检查）`
2. `Smoke E2E（冒烟端到端）` 脚本
3. 关键链路指标：`ingest/chat/render/export` 延迟与成功率

---

## 4. 实施规则（Engineering Rules）

1. 禁止跳过 `Slice 0` 直接写业务逻辑。
2. 每次只开一个 `Slice`，跨切片需求延后入栈。
3. 对外接口仅允许增量演进，不允许同版本破坏式变更。
4. 所有失败必须返回枚举化错误码，不允许前端靠字符串猜测。

---

## 5. 近期执行清单（Next 2 Weeks）

Week 1：

1. 完成 `Slice 0` 契约评审并冻结。
2. 完成 `Slice 1` 和 `Slice 2`，实现真实 chat 决策流转。

Week 2：

1. 完成 `Slice 3` 与 `Slice 4`，实现“可看 + 可检索”。
2. 启动 `Slice 5`，打通补丁式微调最小闭环。

里程碑（Milestone）：

1. M1：`chat -> decision card` 全真实数据。
2. M2：`chat -> contract -> render` 全链路可回归。
3. M3：`ingest -> index -> refine -> export` MVP 闭环。

