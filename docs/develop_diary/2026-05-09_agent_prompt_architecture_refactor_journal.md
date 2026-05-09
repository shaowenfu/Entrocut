# 2026-05-09 Agent Prompt 架构重构日记

今天的核心工作是把 `Agent` 的上下文组织方式从旧的 `planner_input JSON` 迁移到新的集中式提示词编排。

旧架构的问题不在于 `system message` 和 `user message` 怎么拆，而在于上下文事实、工具能力、运行态集合和决策输出混在一起：模型既要理解业务素材，又要理解很多历史字段和能力开关。结果是 `Prompt（提示词）` 变厚、工具边界变虚、测试里也沉淀了不少过时断言。

这次重构的北极星目标是：

`让 Agent 面对的是一个真实、完整、低噪声的剪辑工作台，而不是一份内部运行态快照。`

## 1. Context Assembler 集中化

`core/application/context.py` 已从旧的结构化 `planner_input JSON` 生成器，改成集中式 `Context Assembler（上下文编排器）`。

现在一轮完整 `Prompt（提示词）` 由同一个入口生成：

1. 静态 `Agent Prompt（智能体提示词）`
2. 项目与草稿状态
3. 素材、片段、镜头和故事线事实
4. 对话历史
5. 当前工具观察结果
6. 工具说明与调用契约
7. 严格 JSON 输出格式

这里刻意没有继续拆出过多中间层。当前阶段最重要的是把上下文编排逻辑集中，降低跨文件跳转成本，而不是提前设计一个过度通用的 Prompt framework。

## 2. 删除冗余能力噪声

按最终方案，`Prompt（提示词）` 中删除了两类无效模块：

1. `Tool Availability（工具可用性）`
2. `Workspace Capability（工作区能力）`

这些布尔值对模型没有实际决策价值。工具是否能用，应通过工具说明、当前项目事实和服务端校验共同表达，而不是把内部 capability 直接塞给模型。

新的工具部分改为解释：

1. 工具的业务作用
2. 工具背后的工作原理
3. 什么时候应该调用
4. 什么时候禁止调用
5. 输入和输出的最小契约

这样模型知道“为什么调用工具”，而不是只看到一组 `enabled: true`。

## 3. PlannerDecisionModel 收缩

`PlannerDecisionModel（规划决策模型）` 已删除历史冗余字段：

1. `reasoning_summary`
2. `tool_input_summary`
3. `draft_strategy`

当前决策模型只保留真正影响执行流的字段：

```json
{
  "status": "requires_tool | final",
  "tool_name": "read | retrieve | inspect | patch | preview | none",
  "tool_input": {},
  "assistant_reply": "面向用户的回复",
  "current_focus": {
    "target_type": "project | storyline | scene | shot | clip",
    "target_id": "..."
  }
}
```

`current_focus` 保持必填，因为它是后续 UI 聚焦、连续对话和局部编辑的重要业务事实。模型不需要暴露推理摘要，也不需要用 `draft_strategy` 触发隐藏副作用。

## 4. 工具契约升级

这次把工具契约改成更接近真实剪辑动作的形态。

`read` 是低成本读取工具，用来让模型按层级查看项目事实。`target_type` 支持：

1. `draft_tree`
2. `storyline`
3. `scene`
4. `shot`
5. `clip`

其中 `storyline` 是必要的。它表达“成片叙事结构”，不同于 `draft_tree` 的原始树状数据，也不同于 `scene / shot / clip` 的局部节点。

`retrieve` 只做粗召回，返回候选 `clip`。它不能替模型判断视觉细节，也不能直接改草稿。

`inspect` 是视觉检查工具，入参改为 `inspection_goal`。它负责把具体 `clip` 看清楚，输出视觉描述和不确定性，不承担比较、排序和剪辑决策。

`patch` 从旧的模糊补丁升级为三种明确动作：

1. `insert_shot`
2. `replace_shot`
3. `delete_shot`

`clip_alias` 已删除。它不能稳定提升表达能力，反而会制造 ID 映射和上下文对齐成本。新的 `patch` 只接受真实业务 ID。

`preview` 保持为预览生成工具，只在已有可预览草稿时使用。

## 5. Runtime State 的边界

这次没有把所有历史 `runtime_state` 数据结构一次性从持久化层删除。

原因是当前前端工作区、历史项目加载和部分任务状态仍会经过这些字段。直接删除会把一次 Prompt 重构扩大成状态迁移工程，风险和收益不匹配。

实际落地策略是：

1. `Prompt（提示词）` 不再依赖旧的 `runtime_state / focus_state / retrieval_state / capabilities`
2. 工具执行不再依赖旧的 `tool_input_summary / draft_strategy`
3. 历史数据读取时做最小兼容迁移，例如把旧 `reasoning_summary` 映射到 `assistant_reply`
4. 后续清理任务已单独落到 `docs/tasks`，避免和本次架构重构耦合

这符合当前目标：先切断旧架构对 Agent 决策的影响，再逐步清理遗留运行态集合。

## 6. 前端字段同步

前端同步把 Assistant turn 的展示字段从 `reasoning_summary` 切到 `assistant_reply`。

涉及：

1. `client/src/services/coreClient.ts`
2. `client/src/store/useWorkspaceStore.ts`
3. `client/src/pages/WorkspacePage.tsx`

这样前后端契约表达一致：这是给用户看的回复，不是模型的推理摘要。

## 7. 测试清理与更新

测试侧主要删除或改写了过时断言：

1. 不再要求 planner 请求必须有两条 messages
2. 不再断言旧 `planner_input JSON`
3. 不再断言 `reasoning_summary / tool_input_summary / draft_strategy`
4. 删除“final 决策隐式生成 placeholder first cut”的旧行为
5. `retrieve / inspect / patch` 测试改为新工具契约
6. `export` 测试改成先显式 `patch` 生成草稿，再执行导出

这次错误排查的根因也很明确：测试 mock 仍返回旧版 `PlannerDecisionModel`，而真实模型已经禁止额外字段并要求 `current_focus`。更新 mock 后，服务端 orchestration 能正常完成。

## 8. 验证结果

用户已在本地执行完整 core 测试：

```bash
source core/venv/bin/activate
uv run python -m unittest discover core/tests
```

结果：

```text
Ran 36 tests in 11.470s
OK
```

测试输出里的：

```text
Asset import failed: segmenter unavailable
```

来自故意模拟素材切分失败的测试路径，属于预期日志，不是失败。

前端类型检查也已验证：

```bash
npm --prefix client run typecheck
```

结果通过。

## 9. 后续注意

1. 不要重新把 `capabilities`、`retrieval_state` 这类内部运行态塞回 `Prompt（提示词）`
2. `Inspect` 只能看画面，不能做候选选择
3. `Retrieve` 只能召回候选，不能替代视觉判断
4. `Patch` 只能表达明确的剪辑动作，不应恢复模糊 `draft_strategy`
5. 旧 `runtime_state` 的彻底删除应按任务清单单独推进，避免破坏历史项目兼容
