# 契约评审清单（Contract Baseline Review）

版本：`v1.0`  
目标：提供一份可直接评审、可直接签字冻结的 `Contract Baseline（契约基线）` 清单。  
范围：适用于任一功能切片开始前的契约冻结，不涉及实现代码。

---

## 1. 评审目标与冻结结果

本次评审结束后，必须冻结以下 5 类契约：

1. `EntroVideoProject`（工程主契约）
2. `ChatRequest`（对话请求）
3. `AgentDecision`（对话响应决策）
4. `Patch/Ops`（增量修改语义）
5. `ErrorEnvelope`（统一错误结构）

冻结输出要求：

1. 三端同构：`client TypeScript` / `server Pydantic` / `core Pydantic or Dataclass`。
2. 所有时间统一 `ms`，禁止混用 `s` 或 `HH:MM:SS` 作为存储值。
3. 所有可空字段明确 `nullable` 语义与缺省行为。

---

## 2. 契约清单（Canonical Contracts）

## 2.1 EntroVideoProject（工程主契约）

必选字段（Must）：

1. `contract_version: string`
2. `project_id: string`
3. `user_id: string`
4. `updated_at: string (ISO-8601)`
5. `assets: SourceAsset[]`
6. `clip_pool: AtomicClip[]`
7. `timeline: Timeline`
8. `reasoning_summary: string`

约束（Constraints）：

1. `reasoning_summary` 不允许空字符串。
2. `timeline.items[].source_clip_id` 必须引用 `clip_pool` 中已存在 `clip_id`。
3. `filters` 在 MVP 仅允许 `speed` 与 `volume_db`。

---

## 2.2 ChatRequest（对话请求）

必选字段（Must）：

1. `project_id: string`
2. `session_id: string`
3. `user_id: string`
4. `message: string`

可选字段（Optional）：

1. `context.asset_ids: string[]`
2. `context.selected_item_id: string`
3. `context.target_duration_ms: number`
4. `current_project: EntroVideoProject`

约束（Constraints）：

1. `message.trim().length > 0`。
2. `target_duration_ms > 0`（若提供）。
3. `current_project.contract_version` 必须可被服务端识别。

---

## 2.3 AgentDecision（对话决策响应）

字段结构：

1. `decision_type: UPDATE_PROJECT_CONTRACT | APPLY_PATCH_ONLY | ASK_USER_CLARIFICATION`
2. `project: EntroVideoProject | null`
3. `patch: PatchPayload | null`
4. `reasoning_summary: string`
5. `ops: Operation[]`
6. `meta.request_id: string`
7. `meta.latency_ms: number`

约束（Constraints）：

1. `project` 与 `patch` 至少一个非空。
2. `reasoning_summary` 必填。
3. `ops` 必须结构化对象，不允许 `string[]`。

---

## 2.4 Patch/Ops（补丁与操作语义）

MVP 最小操作集合（建议冻结）：

1. `replace_timeline_item`
2. `insert_timeline_item`
3. `delete_timeline_item`
4. `update_item_filters`

`Operation` 建议结构：

1. `op: string`
2. `target_item_id?: string`
3. `track_id?: string`
4. `payload?: object`

约束（Constraints）：

1. 每个 `op` 必须可幂等重放或可检测重复执行。
2. 服务端返回 `ops` 时必须带最小上下文（至少能定位到目标 item）。

---

## 2.5 ErrorEnvelope（统一错误结构）

结构：

1. `error.code: string`
2. `error.message: string`
3. `error.details.request_id?: string`
4. `error.details.retryable?: boolean`

约束（Constraints）：

1. `code` 必须在错误码表枚举中。
2. `message` 面向调用方可读，不泄露内部实现路径/密钥。
3. 前端只基于 `code` 分支，不基于 `message` 文本分支。

---

## 3. 字段级评审检查表（Review Checklist）

## 3.1 类型与可空性

1. [ ] 每个字段有明确类型定义。
2. [ ] 每个字段明确 `required/optional/nullable`。
3. [ ] 所有数组字段定义空数组语义（空即无数据，而非失败）。

## 3.2 单位与格式

1. [ ] 所有时间字段统一 `ms`。
2. [ ] 时间戳统一 `ISO-8601`。
3. [ ] `id` 字段格式统一（是否允许 UUID 或自增前缀）。

## 3.3 分支语义

1. [ ] `decision_type` 三种分支在前端有确定处理策略。
2. [ ] `APPLY_PATCH_ONLY` 时 `patch/ops` 最小可执行。
3. [ ] `ASK_USER_CLARIFICATION` 时有明确 `next_question` 表达方案（若暂不做需明确 Non-goal）。

## 3.4 兼容策略

1. [ ] `contract_version` 升级规则（Major/Minor）明确。
2. [ ] 旧版本请求处理策略明确（拒绝/降级）。
3. [ ] 兼容策略写入 `docs/04_CONTRACTS.md`。

## 3.5 错误语义

1. [ ] `core/server` 错误码无重名歧义。
2. [ ] `retryable` 语义统一（哪些错误可重试）。
3. [ ] `request_id` 在失败时必回传。

---

## 4. 三端映射清单（Mapping）

## 4.1 Client（TypeScript）

1. `src/domain/contracts.ts`（建议新增）：定义全部契约类型。
2. `src/services/*`：输入输出严格使用契约类型，不再内嵌 `any`。
3. `src/view-model/*`（建议新增）：将契约映射为 UI 展示字段。

## 4.2 Server（Pydantic）

1. `server/models/contracts.py`（建议新增）：定义请求响应模型。
2. `server/routes/chat.py`（建议新增）：仅接受/返回模型对象。
3. `server` 内部策略输出必须在出接口前完成契约校验。

## 4.3 Core（Pydantic/Dataclass）

1. `core/models/contracts.py`（建议新增）：定义 render/ingest 相关模型。
2. `core` 渲染入口只接受 `EntroVideoProject`，禁止自由 JSON。

---

## 5. 评审会议议程（60 分钟）

1. 10 分钟：过一遍 5 类契约与 MVP 边界。
2. 20 分钟：逐字段过 `required/optional/nullable/default`。
3. 15 分钟：逐分支过 `decision_type` 与 `patch ops`。
4. 10 分钟：确认错误码表与 `retryable` 语义。
5. 5 分钟：冻结版本号与变更流程。

会议输出物：

1. 冻结版契约文档链接。
2. 待办项清单（仅允许 `non-blocking` 项）。
3. 责任人与截止时间。

---

## 6. 评审时必须明确的开放问题（Blocking Questions）

1. `APPLY_PATCH_ONLY` 的 `patch` 是否采用 `JSON Patch（RFC6902）`，还是自定义 `Ops DSL（操作描述语法）`？
2. `ASK_USER_CLARIFICATION` 是否需要独立字段 `clarification_question`？
3. `current_project` 过大时，是否支持传 `project_ref + hash` 以减少传输？
4. `ops` 与 `reasoning_summary` 的最小长度/最大长度约束是多少？
5. `contract_version` 不兼容时，前端是阻断还是提示升级后重试？

处理规则：

1. 上述问题在当前评审轮次必须“明确决策”或“明确暂缓并写入 Non-goal”。
2. 不允许带着未定语义进入代码实现阶段。

---

## 7. 冻结签字（Sign-off）

1. Product（产品）：
2. Client（前端）：
3. Core（本地引擎）：
4. Server（云端编排）：
5. Architecture（架构）：

签字标准：

1. 本清单 `3.x` 全部打勾。
2. `6` 章开放问题全部落地结论。
3. 版本写入：`contract_version = 1.0.0`（或会议确认版本）。
