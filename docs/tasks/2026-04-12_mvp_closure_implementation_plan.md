# EntroCut MVP 四阶段收口任务执行文档

日期：2026-04-12  
文档定位：任务执行文档  
适用对象：负责 `core / server / client` 收口的工程师  
使用方式：按阶段推进；每阶段内部按任务顺序执行；完成后逐项勾验收条件

---

## 1. 文档目标

本文档不是再做一轮现状分析，而是把 `docs/tasks/2026-04-12_mvp_closure_implementation_plan.md` 原有分析内容重构为一份可直接执行的完整任务文档，目标是指导工程师完成整个四阶段的 `MVP` 收口工作。

本文档覆盖：

1. 最终 `MVP` 定义
2. 当前基线与未完成项
3. 四阶段任务拆解
4. 每阶段的模块改造点
5. 数据契约与事件契约调整
6. 测试与验收方案
7. 风险与实施顺序
8. 非 `P0/P1` 之外的后续增强项

本文档的最终目标只有一个：

`让 EntroCut 从“基建闭环已完成、执行层仍有占位”推进到“用户可与 agent 对话，agent 可完成真实检索、草案修改、预览合成、导出，并向前端展示全过程”的完整 MVP。`

---

## 2. MVP 完成定义

本轮收口完成后，系统应满足以下能力。

### 2.1 用户视角完成定义

用户可以：

1. 创建项目并导入本地视频素材。
2. 等待素材完成切分与索引。
3. 用自然语言向 `agent` 描述剪辑目标。
4. 让 `agent` 调用工具进行候选检索、候选检查、草案修改。
5. 在前端看到 `agent` 正在执行的步骤与中间状态。
6. 播放当前 `EditDraft` 对应的真实 preview 视频。
7. 导出真实可播放的最终成片。

### 2.2 系统视角完成定义

系统必须具备：

1. 真实 `retrieval`
2. 可解释的 `inspect`
3. 正式 `EditDraftPatch`
4. 真实 `preview render`
5. 真实 `export render`
6. 基于 `WebSocket` 的过程事件展示
7. 预览与导出共用一套 `render plan`

### 2.3 明确非目标

本轮不做：

1. 传统时间线编辑器
2. 高级特效、转场、字幕动画
3. 音频节拍分析与自动音乐对拍
4. 多智能体复杂协作
5. 最终生产级质量评分器
6. 大规模自动镜头重排策略搜索

本轮目标是：

`先把 agent 的最小可用执行闭环做实，而不是把整个最终产品一次性做完。`

---

## 3. 当前基线

当前仓库已经完成的部分可以视作本轮任务的稳定基线，不应在无必要情况下推倒重来。

### 3.1 已完成基础设施

1. `core` 已经完成本地持久化：
   - `SQLite`
   - 项目工作目录
   - `auth session mirror`
2. 状态契约已收口为：
   - `summary_state`
   - `media_summary`
   - `runtime_state`
   - `capabilities`
   - `active_tasks`
3. 素材导入已真实落地：
   - `scenedetect`
   - `ffmpeg`
   - 证据图拼接
   - `server /v1/assets/vectorize`
4. `chat -> planner -> minimal tool loop -> draft writeback` 已经打通。
5. 前端已可消费：
   - `workspace.snapshot`
   - `task.updated`
   - `edit_draft.updated`
   - `chat.turn.created`
   - `project.updated`
   - `asset.updated`
   - `project.summary.updated`
   - `capabilities.updated`

### 3.2 当前真正未完成的部分

当前不是“没有骨架”，而是以下执行层仍未收口：

1. `retrieve` 没接真实向量检索
2. `inspect` 没接真实证据查看
3. `patch` 不是正式 patch 协议
4. `preview` 不产出真实视频
5. `export` 还是占位文件
6. 前端没有展示真实 `agent` 执行轨迹
7. 前端预览区播放的仍主要是源素材，不是草案预览产物

---

## 4. 总体实施原则

本轮收口必须遵守以下原则。

### 4.1 预览优先于导出

先做真实 preview，再做真实 export。  
原因：

1. preview 是最短验证路径
2. preview 决定 export 技术路径
3. 没有 preview，无法做中间态验证

### 4.2 render plan 单一事实源

preview 和 export 必须共用同一套 `render plan`。  
不允许：

1. preview 一套拼接逻辑
2. export 另一套拼接逻辑

否则后续必然出现“预览与导出不一致”。

### 4.3 patch 统一入口

所有草案修改必须通过统一 `apply_edit_draft_patch(...)` 入口。  
不允许在多个工具里直接手写修改 `draft.shots/scenes`。

### 4.4 agent 负责 orchestration，不负责重型实现细节

保持边界：

1. `agent.py`
   - 只负责 planner loop 与工具编排
2. `store.py`
   - 只负责状态写回、任务调度、事件广播
3. 新增执行模块
   - 负责 retrieval、inspection、patching、rendering

### 4.5 事件要比 UI 更先稳定

前端过程展示应建立在稳定事件契约之上，而不是先写页面再反推后端。  
顺序应为：

1. 定义事件
2. 后端发事件
3. 前端消费事件
4. 页面展示事件

---

## 5. 实施范围总览

本轮任务分四个阶段：

1. `Phase 1`
   - 真实 `preview render`
2. `Phase 2`
   - 真实 `retrieval + inspect`
3. `Phase 3`
   - 正式化 `patch writeback`
4. `Phase 4`
   - 真实 `export + process visualization`

同时补一条横向工作线：

1. clip 语义增强
2. 测试补齐
3. 文档更新
4. 端到端烟测

---

## 6. 目标模块与建议文件落点

### 6.1 Core 侧新增或改造模块

建议新增：

1. `core/rendering.py`
   - `render plan`
   - preview/export 渲染执行
2. `core/retrieval.py`
   - 调 `server /v1/assets/retrieval`
   - 结果标准化
3. `core/inspection.py`
   - 候选证据读取与格式化
4. `core/patching.py`
   - `EditDraftPatch`
   - patch 应用逻辑

重点改造：

1. `core/agent.py`
2. `core/store.py`
3. `core/schemas.py`
4. `core/context.py`

### 6.2 Server 侧改造模块

重点改造：

1. `server/app/schemas/assets.py`
2. `server/app/services/vector.py`
3. `server/app/api/routes/assets.py`

目标不是重写 server，而是确保 retrieval/vectorize 的输入输出契约适合 `core` 使用。

### 6.3 Client 侧改造模块

重点改造：

1. `client/src/store/useWorkspaceStore.ts`
2. `client/src/pages/WorkspacePage.tsx`
3. `client/src/services/coreClient.ts`
4. `client/src/services/localMediaRegistry.ts`

必要时新增：

1. `client/src/components/...`
   - `AgentTimeline`
   - `PreviewBadge`
   - `PreviewSourceSwitcher`

---

## 7. 阶段依赖关系

阶段之间存在明确依赖，不能随意打乱。

### 7.1 依赖图

1. `Phase 1 preview render`
   - 是 `Phase 4 export` 的前置
2. `Phase 2 retrieval/inspect`
   - 是 `Phase 3 patch` 的高质量输入前置
3. `Phase 3 patch`
   - 是 `Phase 1/4 render` 的高质量输入来源
4. `Phase 4 process visualization`
   - 依赖前 1-3 阶段产生真实执行事件与产物

### 7.2 推荐执行顺序

建议实际工程顺序：

1. 先打 `rendering` 骨架与 `render plan`
2. 同时补 `preview` 最小链
3. 再接真实 retrieval
4. 再补 inspect
5. 再正式化 patch
6. 再把 export 切到真实渲染
7. 最后补前端过程展示与产品语义收口

---

## 8. Phase 1：真实 Preview Render

## 8.1 阶段目标

让 `EditDraft` 可以生成真实 preview 视频，并成为后续 export 的技术基础。

### 阶段完成定义

满足以下条件即视为 `Phase 1` 完成：

1. 输入一个含至少一个 shot 的 `EditDraft`
2. 系统能生成一个真实视频文件到 `preview/`
3. 前端能够拿到 preview 产物路径
4. 前端能够播放这个 preview

## 8.2 子任务拆解

### 任务 1：定义 render plan

目标：

1. 将 `EditDraft.shots` 转换为统一 `render plan`

建议新增 schema：

1. `RenderSegment`
   - `asset_id`
   - `source_path`
   - `source_in_ms`
   - `source_out_ms`
   - `shot_id`
   - `scene_id`
   - `order`
2. `RenderPlan`
   - `project_id`
   - `draft_id`
   - `draft_version`
   - `segments`
   - `estimated_duration_ms`

建议落点：

1. `core/schemas.py`
2. `core/rendering.py`

验收：

1. 能稳定从 draft 生成有序 segment 列表
2. 对空 shot、非法 source range 有明确错误

### 任务 2：实现 preview renderer

目标：

1. 根据 `RenderPlan` 生成 preview 视频

建议实现：

1. `build_render_plan(draft, asset_lookup)`
2. `render_preview(plan, output_path, quality="preview")`

建议策略：

1. 初版只支持视频片段拼接
2. 暂不处理复杂音频混合
3. 对缺失素材直接失败，不做静默跳过

建议落点：

1. `core/rendering.py`

验收：

1. 输出真实 `mp4`
2. 可被本地播放器播放
3. 失败时有明确错误语义

### 任务 3：在 core/store 中增加 preview 任务执行

目标：

1. preview 成为正式后台任务

需要补：

1. `TaskType`
   - 增加 `preview`
2. `TaskSlot`
   - 初版继续放 `agent` 或新增 `preview`

推荐：

1. 为避免把 `preview` 与 `chat` 强绑定，建议新增独立 `preview` slot
2. 如果暂不改大契约，也可先复用 `export` slot，但中期应拆开

建议落点：

1. `core/schemas.py`
2. `core/store.py`

验收：

1. preview 有独立任务状态
2. 任务成功后能写回 preview 产物信息

### 任务 4：新增 preview 结果事件

目标：

1. 让前端拿到真实 preview artifact

建议新增事件：

1. `preview.completed`
   - 包含：
     - `draft_version`
     - `output_url`
     - `duration_ms`
     - `render_profile`

建议同时更新：

1. `workspace.snapshot`
   - 可包含最近一次 preview artifact

建议落点：

1. `core/store.py`
2. `core/schemas.py`
3. `client/src/services/coreClient.ts`

验收：

1. 前端无需轮询即可拿到 preview 成果

## 8.3 Phase 1 文件改动清单

至少涉及：

1. `core/schemas.py`
2. `core/rendering.py`
3. `core/store.py`
4. `client/src/services/coreClient.ts`
5. `client/src/store/useWorkspaceStore.ts`
6. `client/src/pages/WorkspacePage.tsx`

## 8.4 Phase 1 测试

需要新增：

1. `core` 单元测试
   - `build_render_plan`
2. `core` 集成测试
   - preview 任务成功生成真实文件
3. 前端状态测试
   - `preview.completed` 事件处理

---

## 9. Phase 2：真实 Retrieval + Inspect

## 9.1 阶段目标

让 `agent` 使用真实向量检索，并能对候选进行证据级检查。

### 阶段完成定义

满足以下条件即视为 `Phase 2` 完成：

1. retrieval 不再依赖本地字符串匹配
2. retrieval 结果来自 `server /v1/assets/retrieval`
3. inspect 能返回可解释候选信息
4. planner 可以基于这些结果继续 patch 或 preview

## 9.2 子任务拆解

### 任务 1：定义 retrieval 契约

目标：

1. 在 `core` 和 `server` 之间收口一套稳定检索契约

建议请求字段：

1. `project_id`
2. `query_text`
3. `topk`
4. 可选：
   - `scene_id`
   - `shot_id`
   - `scope_type`

建议响应字段：

1. `matches`
   - `clip_id`
   - `asset_id`
   - `score`
   - `source_start_ms`
   - `source_end_ms`
   - `frame_count`

建议落点：

1. `server/app/schemas/assets.py`
2. `client/src/services/coreClient.ts`
3. `core/retrieval.py`

### 任务 2：实现 core retrieval executor

目标：

1. 将 `agent retrieve` 从本地 fallback 改成真实 server call

建议实现：

1. `retrieve_candidates(...)`
2. 内部完成：
   - 请求组装
   - 鉴权
   - server 响应标准化
   - 错误映射

建议落点：

1. `core/retrieval.py`
2. `core/agent.py`

验收：

1. `agent` 的 `retrieve` 结果来自 server
2. 失败时保留明确 error code

### 任务 3：定义 inspection 证据结构

目标：

1. inspect 不再只返回 clip dump，而是返回决策证据

建议 inspection 输出包含：

1. `clip`
2. `retrieval_score`
3. `evidence_image_ref`
4. `summary`
5. `why_selected`

如果当前没有稳定图片路径，可先返回：

1. `thumbnail_ref`
2. `source range`
3. `score`
4. `visual_desc`

中期再提升为真正 evidence image path。

建议落点：

1. `core/inspection.py`
2. `core/schemas.py`
3. `core/agent.py`

### 任务 4：把 retrieval/inspect 写回 runtime_state

目标：

1. retrieval/inspect 的结果成为 runtime 事实，而不是本轮局部变量

需要补强字段：

1. `retrieval_state.last_query`
2. `retrieval_state.candidate_clip_ids`
3. 可新增：
   - `candidate_scores`
   - `selected_candidate_id`
   - `inspection_summary`

建议落点：

1. `core/schemas.py`
2. `core/agent.py`

## 9.3 Phase 2 文件改动清单

至少涉及：

1. `core/schemas.py`
2. `core/retrieval.py`
3. `core/inspection.py`
4. `core/agent.py`
5. `core/context.py`
6. `server/app/schemas/assets.py`
7. `server/app/services/vector.py`
8. `server/app/api/routes/assets.py`

## 9.4 Phase 2 测试

需要新增：

1. retrieval 请求/响应单元测试
2. retrieval 集成测试
3. inspect 输出结构测试
4. runtime state 写回测试

---

## 10. Phase 3：正式化 Patch Writeback

## 10.1 阶段目标

将 patch 从临时写回逻辑升级为正式 `EditDraftPatch` 协议。

### 阶段完成定义

满足以下条件即视为 `Phase 3` 完成：

1. patch 有正式 schema
2. 所有草案修改走统一入口
3. 支持最小必要编辑动作
4. patch 后可直接进入 preview/render

## 10.2 子任务拆解

### 任务 1：定义 EditDraftPatch schema

建议结构：

1. `EditDraftPatch`
   - `operations`
   - `reasoning_summary`
   - `scope`
2. `PatchOperation`
   - `insert_shot`
   - `replace_shot`
   - `trim_shot`
   - `delete_shot`
   - `reorder_shot`
   - 可选 `update_scene`

建议落点：

1. `core/schemas.py`

### 任务 2：实现统一 patch apply

目标：

1. 所有 draft 修改都收口到一个函数

建议接口：

1. `apply_edit_draft_patch(draft, patch) -> draft`

要求：

1. 不静默修正非法 patch
2. 非法 patch 直接报错
3. 保证 `draft.version` 递增
4. 保证 `selected_scene_id/selected_shot_id` 一致

建议落点：

1. `core/patching.py`

### 任务 3：agent patch 工具改为生成或消费正式 patch

目标：

1. `agent` 不再直接拼 `ShotModel/SceneModel`

建议方案：

1. planner 输出中携带结构化 patch payload
2. `agent` 调 `apply_edit_draft_patch`

如果当前 planner 尚不稳定，可过渡为：

1. `agent` 内部先把 tool input 转成正式 patch
2. 再统一 apply

但最终不要继续保留“临时拼 draft”逻辑。

### 任务 4：context 中补充 patch 可执行约束

目标：

1. planner 知道当前允许哪些 patch
2. planner 知道当前 scope 与候选约束

建议补：

1. 当前 `selected_scene_id`
2. 当前 `selected_shot_id`
3. 当前可 patch 的对象范围
4. 当前 candidate clip 来源

建议落点：

1. `core/context.py`

## 10.3 Phase 3 文件改动清单

至少涉及：

1. `core/schemas.py`
2. `core/patching.py`
3. `core/agent.py`
4. `core/context.py`
5. `core/store.py`

## 10.4 Phase 3 测试

需要新增：

1. patch apply 单元测试
2. 各 patch operation 行为测试
3. 非法 patch 错误语义测试
4. patch 后 preview 结果回归测试

---

## 11. Phase 4：真实 Export + Process Visualization

## 11.1 阶段目标

让系统具备：

1. 真实导出
2. agent 过程可视化
3. preview/source 语义清晰的 UI

### 阶段完成定义

满足以下条件即视为 `Phase 4` 完成：

1. export 输出真实视频文件
2. 前端能展示 agent 过程轨迹
3. 前端预览区优先播放 draft preview
4. 用户能明确分辨 source 与 draft

## 11.2 子任务拆解

### 任务 1：export 切换到真实 renderer

目标：

1. 复用 `RenderPlan`
2. 用真实渲染替换 placeholder export

建议接口：

1. `render_export(plan, output_path, quality, resolution)`

要求：

1. 与 preview 共享 segment 拼接逻辑
2. 只在 profile/编码参数上区分

建议落点：

1. `core/rendering.py`
2. `core/store.py`

### 任务 2：定义 agent step 状态结构

目标：

1. 让 `agent.step.updated` 足够被 UI 展示

建议统一字段：

1. `phase`
2. `summary`
3. `details`
4. `iteration`
5. `status`
6. `emitted_at`

当前已有事件可沿用，但要保证字段稳定。

建议落点：

1. `core/agent.py`
2. `core/schemas.py`
3. `client/src/services/coreClient.ts`

### 任务 3：前端消费 agent.step.updated

目标：

1. 在 store 中维护 `agentSteps`

建议新增状态：

1. `agentSteps: AgentStepItem[]`

建议 reducer 行为：

1. 按序追加
2. 同步更新当前 thinking 状态
3. 新 chat 开始时清理上一轮步骤

建议落点：

1. `client/src/store/useWorkspaceStore.ts`
2. `client/src/services/coreClient.ts`

### 任务 4：页面增加过程时间线

目标：

1. 让用户看到 agent 做了什么

建议展示内容：

1. loop started
2. planner context assembled
3. planner decision received
4. tool requested
5. observation recorded
6. draft updated
7. loop finalized

建议 UI 位置：

1. `AI Copilot` 区域内 chat 线程上方或下方单独一栏

### 任务 5：预览区语义收口

目标：

1. 不再混淆 source 与 draft

建议实现：

1. 预览区优先级：
   - draft preview
   - source asset
2. 页面上显式标识：
   - `Draft Preview`
   - `Source Media`
3. 若当前 preview 版本落后于 draft.version，显示 `stale preview` 提示

## 11.3 Phase 4 文件改动清单

至少涉及：

1. `core/rendering.py`
2. `core/store.py`
3. `core/agent.py`
4. `client/src/services/coreClient.ts`
5. `client/src/store/useWorkspaceStore.ts`
6. `client/src/pages/WorkspacePage.tsx`
7. 可选 `client/src/components/...`

## 11.4 Phase 4 测试

需要新增：

1. export 集成测试
2. `agent.step.updated` reducer 测试
3. 页面过程时间线渲染测试
4. preview/source 切换测试

---

## 12. 横向任务线 A：clip 语义增强

这条线不是四阶段主链的一部分，但建议在 `Phase 2-3` 期间同步推进。

### 目标

提升 clip 可读性与 retrieval fallback 质量。

### 任务

1. 在素材导入完成后补充 clip 语义摘要
2. 回写：
   - `visual_desc`
   - `semantic_tags`
3. 保证这些内容可被 planner context 使用

### 推荐时机

1. `Phase 2 retrieval` 接通后立即推进

### 验收

1. 新导入 clip 不再只有占位描述
2. inspect 输出更具可读性

---

## 13. 横向任务线 B：测试矩阵补齐

这一轮必须同步补测试，否则后续重构会失控。

### 13.1 Core 单元测试

必须补：

1. `render plan`
2. `rendering`
3. `retrieval response normalize`
4. `inspection formatting`
5. `patch apply`

### 13.2 Core 集成测试

必须补：

1. preview 任务完整链
2. retrieval 完整链
3. patch + preview 连续链
4. export 完整链
5. 事件发射顺序测试

### 13.3 Client 测试

必须补：

1. `agent.step.updated` store reducer
2. preview 事件处理
3. 预览区 source/draft 选择逻辑
4. timeline 渲染

### 13.4 E2E 烟测

至少补一条：

1. 创建项目
2. 导入素材
3. 索引完成
4. 发送 chat
5. draft 被修改
6. preview 生成
7. export 生成

---

## 14. 横向任务线 C：文档与契约同步

本轮完成后，必须同步更新文档，避免代码和文档再度分叉。

需要更新：

1. `core/README.md`
2. `client/README.md`
3. `docs/store/01_core_api_ws_contract.md`
4. 如 retrieval 契约变化较大，可新增 `docs/editing/...` 文档说明

更新重点：

1. preview/export 已真实化
2. `agent.step.updated` 已进入前端展示链
3. patch 已正式 schema 化
4. retrieval 已接真实索引

---

## 15. 任务执行顺序建议

下面是推荐的实际工程排期顺序。

### 15.1 第一轮

1. 建 `core/rendering.py`
2. 定义 `RenderPlan`
3. 打通 preview 真实渲染
4. 前端能拿到 preview 并播放

### 15.2 第二轮

1. 定义 retrieval 契约
2. 实现 `core/retrieval.py`
3. 改造 `agent retrieve`
4. 实现 inspection 输出

### 15.3 第三轮

1. 定义 `EditDraftPatch`
2. 实现 `core/patching.py`
3. 替换当前 patch 临时逻辑
4. 接通 patch -> preview 回归验证

### 15.4 第四轮

1. export 改用真实 renderer
2. 定义和稳定 `agent.step.updated`
3. 前端接 timeline
4. 收口 preview/source UI 语义

### 15.5 第五轮

1. clip 语义增强
2. 文档同步
3. E2E 烟测与回归

---

## 16. 风险清单与规避策略

### 风险 1：preview/export 分叉

规避：

1. 强制共用 `RenderPlan`
2. 强制共用 segment 拼接逻辑

### 风险 2：patch 逻辑四处分散

规避：

1. 一律通过 `apply_edit_draft_patch(...)`
2. 不允许工具层私自改 draft

### 风险 3：前端错误播放 source 冒充 draft

规避：

1. 预览区明确显示当前来源类型
2. 默认优先 draft preview

### 风险 4：retrieval 接通但候选质量依旧差

规避：

1. 在 `Phase 2` 后立即推进 clip 语义增强
2. inspect 输出必须包含 score 与可读摘要

### 风险 5：任务 slot 设计混乱

规避：

1. 预览任务尽量独立
2. 若先复用旧 slot，必须在文档中写清过渡策略

---

## 17. 阶段验收清单

## 17.1 Phase 1 验收

1. preview 生成真实视频
2. preview 可播放
3. 预览产物写入 `preview/`
4. preview 失败有明确错误

## 17.2 Phase 2 验收

1. retrieval 结果来自 server
2. inspect 返回证据级信息
3. runtime_state 反映候选状态

## 17.3 Phase 3 验收

1. patch 有正式 schema
2. patch 走统一 apply 入口
3. patch 结果能驱动 preview

## 17.4 Phase 4 验收

1. export 输出真实视频
2. 前端展示完整 agent 过程
3. preview/source 语义清楚

## 17.5 全局验收

1. 创建项目
2. 导入素材
3. 索引完成
4. 和 agent 对话
5. agent 检索候选
6. agent 修改草案
7. preview 生成并播放
8. export 生成并下载/打开
9. 前端可看到整个过程

---

## 18. 完成后的最终状态

当本执行文档全部完成后，EntroCut 应从当前的：

`基础设施闭环已完成，但执行层与媒体产物层仍有占位`

推进到：

`用户可通过自然语言驱动 agent 完成真实检索、真实 patch、真实预览、真实导出，并在前端看到完整执行过程的 MVP 产品形态。`

---

## 19. 一句话执行建议

如果现在立刻开工，不要先碰更多 planner prompt，也不要先堆新的 UI。

先做：

1. `RenderPlan + Preview Render`
2. `Real Retrieval`
3. `Formal Patch`
4. `Real Export`
5. `Process Timeline`

这是最短、最稳、也最符合当前仓库演进方向的收口路径。
