# EntroCut Agent Prompt Architecture Refactor Task

本文档是实施任务清单，和 `EntroCut_agent_prompt_architecture.md` 的方案说明解耦。执行时以代码真实依赖为准，但不得偏离新 Prompt Architecture（提示词架构）的北极星目标。

## 1. 目标

彻底废弃旧 `planner_input JSON` Context Engineering（上下文工程）架构，改为集中式 Context Assembler（上下文编排器）生成完整 Prompt（提示词）。

最终结果：

1. Agent Loop（智能体循环）每轮发送一份完整 Prompt（提示词）。
2. Prompt（提示词）按 5 个模块固定拼接。
3. PlannerDecisionModel（规划决策模型）只保留必要字段。
4. Tool Contract（工具契约）字段全部确定，不使用省略字段。
5. 删除旧 Runtime State（运行态集合）对 Agent 决策的影响。

## 2. 改造边界

需要修改：

```text
core/contracts/__init__.py
core/application/context.py
core/agent_runtime/agent.py
core/agent_runtime/inspection.py
core/agent_runtime/patching.py
core/agent_runtime/retrieval.py
core/runtime/helpers.py
core/application/store.py
core/tests/*
client/src/services/coreClient.ts
client/src/store/useWorkspaceStore.ts
client/src/pages/WorkspacePage.tsx
```

按实际依赖增减，但不做无关 UI（用户界面）重构。

## 3. 阶段 1：契约清理

- [ ] 修改 `PlannerDecisionModel`，保留字段：
  - [ ] `status`
  - [ ] `tool_name`
  - [ ] `tool_input`
  - [ ] `assistant_reply`
  - [ ] `current_focus`
- [ ] 删除 `PlannerDecisionModel.reasoning_summary`。
- [ ] 删除 `PlannerDecisionModel.tool_input_summary`。
- [ ] 删除 `PlannerDecisionModel.draft_strategy`。
- [ ] 删除 `PlannerDraftStrategy` 类型。
- [ ] 增加 `PlannerFocus` 模型。
- [ ] 收紧 `ToolName` 类型，继续只允许：
  - [ ] `read`
  - [ ] `retrieve`
  - [ ] `inspect`
  - [ ] `patch`
  - [ ] `preview`
- [ ] 增加 `ReadInput` / `ReadOutput` 契约。
- [ ] 增加 `InspectInput` / `InspectOutput` 契约。
- [ ] 增加新版 `PatchInput` / `PatchOutput` 契约。
- [ ] 增加 `PreviewInput` / `PreviewOutput` 契约。

验收标准：

- [ ] 任何 Planner（规划器）响应缺字段都会校验失败。
- [ ] 任何 Tool Input（工具输入）使用旧字段都会校验失败。

## 4. 阶段 2：删除旧 Context Engineering（上下文工程）

- [ ] 删除或废弃 `PlannerRuntimeState`。
- [ ] 删除或废弃 `PlannerContextPacket`。
- [ ] 删除或废弃 `build_planner_context_packet`。
- [ ] 删除或废弃 `build_goal_state`。
- [ ] 删除或废弃 `build_scope_state`。
- [ ] 删除或废弃 `build_project_state`。
- [ ] 删除或废弃 `build_draft_state`。
- [ ] 删除或废弃 `build_media_state`。
- [ ] 删除或废弃 `build_capabilities_state`。
- [ ] 删除或废弃 `build_tool_capability_state`。
- [ ] 删除或废弃 `build_working_memory_state`。
- [ ] 删除或废弃 `build_runtime_state_snapshot`。
- [ ] 删除或废弃 `build_current_user_request_state`。
- [ ] 删除或废弃 `build_runtime_capabilities_state`。
- [ ] 删除或废弃 `build_trace_state`。
- [ ] 删除旧 `planner_input` 生成逻辑。
- [ ] 删除旧测试中对 `planner_input.current_user_request`、`goal`、`scope`、`memory` 的断言。

验收标准：

- [ ] 发给 LLM（大语言模型）的消息中不再出现 `planner_input`。
- [ ] Prompt（提示词）中不再出现 `current_user_request`、`goal_source`、`runtime_capabilities` 等旧结构字段。

## 5. 阶段 3：实现 Context Assembler（上下文编排器）

- [ ] 在 `core/application/context.py` 中集中实现 `build_agent_prompt`。
- [ ] 实现 `render_system_context_and_global_state`。
- [ ] 实现 `render_chat_history`。
- [ ] 实现 `render_current_loop_observations`。
- [ ] 实现 `render_available_tools`。
- [ ] 实现 `render_strict_json_output_contract`。
- [ ] 保持编排逻辑在单文件内可读，不拆成多层 Builder（构建器）。
- [ ] Global TOC（全局目录）只注入 Scene（场景）和 Shot（镜头）骨架。
- [ ] Storyline Digest（故事线摘要）只从 Scene（场景）和 Shot（镜头）的意图字段派生。
- [ ] Chat History（对话历史）只保留最近 5 轮。
- [ ] Tool Observations（工具观测）只注入本轮真实工具结果。
- [ ] Tool Contracts（工具契约）每轮完整注入。

验收标准：

- [ ] 单元测试能断言 Prompt（提示词）包含 5 个固定模块。
- [ ] 单元测试能断言 Prompt（提示词）不包含 Clip（片段）视觉细节，除非来自 Tool Observation（工具观测）。

## 6. 阶段 4：Agent Loop（智能体循环）改造

- [ ] 修改 `_build_planner_messages`，使用 `build_agent_prompt`。
- [ ] 当前阶段将完整 Prompt（提示词）作为单个 System Message（系统消息）或单个消息发送。
- [ ] 删除 `_decision_tool_input` 对 `tool_input_summary` 的兼容。
- [ ] 删除 `_parse_tool_input_summary`。
- [ ] 删除 `draft_strategy` 分支。
- [ ] 删除 Placeholder First Cut（占位初剪）自动兜底。
- [ ] Planner（规划器）返回 `final` 时只写入 `assistant_reply` 和必要操作摘要。
- [ ] Planner（规划器）返回 `requires_tool` 时只执行一个 Tool（工具）。

验收标准：

- [ ] 旧格式 Planner（规划器）响应不再被兼容。
- [ ] Agent Loop（智能体循环）不会基于 `draft_strategy` 自动修改草稿。

## 7. 阶段 5：Read Tool（读取工具）升级

- [ ] 实现 `target_type = "draft_tree"`。
- [ ] 实现 `target_type = "storyline"`。
- [ ] 实现 `target_type = "scene"`。
- [ ] 实现 `target_type = "shot"`。
- [ ] 实现 `target_type = "clip"`。
- [ ] 要求 `draft_tree` 和 `storyline` 的 `target_id` 固定为 `"root"`。
- [ ] 对不存在的 `scene_id` / `shot_id` / `clip_id` 返回稳定错误。
- [ ] 压缩 `ReadOutput.data`，避免返回原始 `EditDraftModel`。

验收标准：

- [ ] `read` 不返回 `runtime_state`。
- [ ] `read` 不返回全量 `assets`。
- [ ] `read(clip)` 才返回 `visual_desc`、`visual_description`、`semantic_tags`。

## 8. 阶段 6：Inspect Tool（检查工具）简化

- [ ] 删除 `clip_alias`。
- [ ] 删除 `question`。
- [ ] 删除 `task_summary`。
- [ ] 改为只接收：
  - [ ] `clip_id`
  - [ ] `inspection_goal`
- [ ] 内部 VLM Prompt（多模态大模型提示词）由 `inspection_goal` 拼接生成。
- [ ] 输出统一为 `InspectOutput`。

验收标准：

- [ ] Planner（规划器）无法通过别名选择 Clip（片段）。
- [ ] `inspect` 不做候选排序。
- [ ] `inspect` 不生成 Patch（补丁）。

## 9. 阶段 7：Patch Tool（补丁工具）升级

- [ ] 修改 Agent 暴露的 `patch` 输入为 `PatchInput.operations`。
- [ ] 支持 `insert_shot`。
- [ ] 支持 `replace_shot`。
- [ ] 支持 `delete_shot`。
- [ ] 删除旧 `clip_id + intent` 单动作接口。
- [ ] 删除旧隐式“插入到末尾”行为。
- [ ] 保留底层 `apply_edit_draft_patch`，但根据新契约收紧校验。
- [ ] 如果底层仍支持 `trim_shot` / `reorder_shot`，不要暴露给 Agent Prompt（智能体提示词）。

验收标准：

- [ ] `patch` 不接受缺少 `operations` 的请求。
- [ ] `patch` 不接受不存在的 `scene_id` / `shot_id` / `clip_id`。
- [ ] `delete_shot` 不删除 Clip（片段）或 Asset（资产）。

## 10. 阶段 8：Retrieve Tool（检索工具）输出压缩

- [ ] 保留 `query` 单字段输入。
- [ ] 返回 `candidates`，不返回原始 Server（服务器）响应。
- [ ] 每个 Candidate（候选）包含：
  - [ ] `clip_id`
  - [ ] `asset_id`
  - [ ] `score`
  - [ ] `source_start_ms`
  - [ ] `source_end_ms`
  - [ ] `visual_desc`
  - [ ] `semantic_tags`
- [ ] 不在 `retrieve` 中输出最终推荐。

验收标准：

- [ ] `retrieve` 输出足以进入 `inspect`。
- [ ] `retrieve` 不承担视觉精判。

## 11. 阶段 9：Preview Tool（预览工具）收紧

- [ ] `preview` 输入只保留 `reason`。
- [ ] `reason` 必填。
- [ ] 输出统一为 `PreviewOutput`。
- [ ] 没有可渲染 Shot（镜头）时返回稳定错误。

验收标准：

- [ ] `preview` 不修改 EditDraft（剪辑草稿）。
- [ ] `preview` 只返回真实渲染结果。

## 12. 阶段 10：Runtime State（运行态集合）彻底清理

- [ ] 梳理 `ProjectRuntimeState` 当前用途。
- [ ] 删除 Agent Prompt（智能体提示词）对 `goal_state` 的依赖。
- [ ] 删除 Agent Prompt（智能体提示词）对 `focus_state` 的依赖。
- [ ] 删除 Agent Prompt（智能体提示词）对 `conversation_state` 的依赖。
- [ ] 删除 Agent Prompt（智能体提示词）对 `retrieval_state` 的依赖。
- [ ] 删除 Agent Prompt（智能体提示词）对 `execution_state` 的依赖。
- [ ] 删除 `read(runtime)` 或类似入口。
- [ ] 若 UI（用户界面）仍需运行态展示，将其拆成 UI State（界面状态），不要进入 Agent Prompt（智能体提示词）。
- [ ] 若后端仍需任务状态，将其保留在 Task（任务）模型，不进入 Agent Prompt（智能体提示词）。

验收标准：

- [ ] Prompt（提示词）中不出现 `runtime_state` 字符串。
- [ ] Tool Contract（工具契约）中不存在 `runtime` target。
- [ ] Agent 决策不依赖旧 `retrieval_state.candidate_clip_ids` 自动补全。

## 13. 阶段 11：前端契约同步

- [ ] 更新 `CoreChatAssistantTurn`。
- [ ] 删除前端对 `reasoning_summary` 的展示依赖。
- [ ] 使用 `assistant_reply` 展示 Assistant（助手）最终回复。
- [ ] 更新 Agent Step（智能体步骤）展示字段。
- [ ] 移除 UI（用户界面）中与 `runtime_state` 强绑定的 Agent 决策展示。
- [ ] 保留项目任务状态、媒体处理状态和预览状态的 UI（用户界面）展示。

验收标准：

- [ ] 前端不再要求 Assistant Turn（助手轮次）必须有 `reasoning_summary`。
- [ ] Chat（聊天）面板显示的是用户可读回复，不显示内部推理摘要。

## 14. 阶段 12：测试

- [ ] 更新 `core/tests/test_context_engineering.py` 或重命名为 Prompt Assembly（提示词编排）测试。
- [ ] 增加 Prompt（提示词）5 模块顺序测试。
- [ ] 增加 Global TOC（全局目录）字段裁剪测试。
- [ ] 增加 Storyline（故事线）生成测试。
- [ ] 增加 PlannerDecisionModel（规划决策模型）新契约测试。
- [ ] 增加旧字段拒绝测试。
- [ ] 增加 `read` 五种 target 测试。
- [ ] 增加 `inspect` 新输入测试。
- [ ] 增加 `patch` 三种操作测试。
- [ ] 增加 `retrieve` 输出压缩测试。
- [ ] 增加 Agent Loop（智能体循环）多轮 Tool Observation（工具观测）测试。

验收标准：

- [ ] `source venv/bin/activate && python -m unittest discover core/tests` 通过。
- [ ] 不使用 `python3` 执行 Python（解释器）命令。

## 15. 最终验收清单

- [ ] 没有 `planner_input`。
- [ ] 没有 `reasoning_summary`。
- [ ] 没有 `tool_input_summary`。
- [ ] 没有 `draft_strategy`。
- [ ] 没有 `clip_alias`。
- [ ] 没有 Agent 可读的 `runtime_state`。
- [ ] Prompt（提示词）由 Context Assembler（上下文编排器）集中生成。
- [ ] Tool Input（工具输入）字段全部确定。
- [ ] Tool Output（工具输出）字段全部确定。
- [ ] Patch Tool（补丁工具）支持 `insert_shot`、`replace_shot`、`delete_shot`。
- [ ] Read Tool（读取工具）支持 `draft_tree`、`storyline`、`scene`、`shot`、`clip`。
- [ ] Inspect Tool（检查工具）只接受 `clip_id` 和 `inspection_goal`。
- [ ] Retrieve Tool（检索工具）只做候选召回。
- [ ] Preview Tool（预览工具）只生成真实预览。
