# 2026-04-13 MVP 闭环与渲染收口日志

## 今日目标
完成 MVP 收口中工程师 A 负责链路：
1. 真实 `preview/export` 渲染。
2. `retrieve/inspect` 接入真实能力。
3. `patch` 正式 schema 化并统一 apply。
4. 前端展示 `agent` 执行时间线与 preview/source 语义。

## 实施摘要

### 1) 渲染链路落地
- 新增 `core/rendering.py`，把 `EditDraft.shots` 统一转换为 `RenderPlan`。
- `preview/export` 复用同一套分段渲染逻辑，避免两套实现分叉。
- `store._run_export` 从占位文本文件切到真实渲染产物输出。

### 2) 检索与证据化 Inspect
- 新增 `core/retrieval.py`，`retrieve` 改为调用 `server /v1/assets/retrieval`。
- 新增 `core/inspection.py`，`inspect` 输出 clip + score + source range + summary。
- runtime state 增加候选分数、已选候选与 inspect 摘要，便于后续 planner 复用。

### 3) Patch 正规化
- 新增 `EditDraftPatchModel` 与 `PatchOperationModel`。
- 新增 `core/patching.py`：所有草案修改收口为 `apply_edit_draft_patch(...)`。
- `agent` 的 patch 工具不再直接拼接 `Shot/Scene`，而是生成并执行正式 patch。

### 4) 前端过程展示
- `workspace store` 新增 `agentSteps/previewResult`，消费 `agent.step.updated` 与 `preview.completed`。
- `WorkspacePage` 新增 `Agent Timeline`。
- 预览区优先播放 Draft Preview，并显式标注 `Draft Preview / Source Media`。

## 踩坑与修正
- 初版测试在无图形依赖环境下会触发 `cv2/libGL` 导入问题；测试中对 ingestion 做局部 stub，保证核心链路可测。
- 前端一次改动引入了 JSX 属性拼接错误，已修复并通过 `npm run typecheck`。

## 当前结论
- MVP 主链从“占位可跑”提升为“可解释、可渲染、可展示过程”的可用闭环。
- 下一步重点应转向：planner 质量、渲染性能、以及 preview stale 提示等产品化细节。
