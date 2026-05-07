# 2026-05-07 Agent Chat UI 集成验收与收尾日记

## 背景

本轮工作承接三份 Agent Chat UI 设计与集成文档：

- `docs/tasks/2026-05-05_agent_chat_ui_component_system_design.md`
- `docs/client/02_agent_chat_ui_interaction_design.md`
- `docs/tasks/2026-05-06_agent_chat_ui_integration_plan.md`

另一位工程师此前提交了 `8ebc174767d49a9727cc09a054682340a3ff3704`，新增了 `AgentChatPanels` 沙盒组件和 `?ui-canvas` 预览入口。该提交对视觉方向有帮助，但它本质是 mock UI（模拟界面），不能直接作为生产 Agent 交互代码使用。

本轮北极星目标是：让真实 `WorkspacePage` 中的 Agent 交互效果流畅、无明显 bug、实用且美观，同时删除已经完成视觉验证使命的沙盒脚手架。

## 验收发现

初始验收时重点发现了几类隐藏风险：

1. `WorkspacePage` 把 `agentSteps` 无条件渲染在所有 `chatTurns` 后面，assistant final message 到达后仍会显示旧执行块，顺序会变成“最终回复之后再显示执行过程”。
2. step 状态只靠“最后一个 step + `isThinking`”推断，忽略了 `CoreAgentStepItem.status` 和 `details.success`，失败态无法稳定表达。
3. artifact 类型识别只看 `phase` 字符串，但 core 实际事件多为 `tool_execution_requested`、`tool_observation_recorded` 等，真实工具名在 `details.tool_name`。
4. `RetrieveArtifact`、`InspectArtifact`、`PatchArtifact` 使用硬编码图片和固定文本，会在生产环境误导用户。
5. 自动折叠没有尊重 `Manual Override`（用户手动覆盖），用户展开后的内容仍可能被定时器折叠。
6. `AgentStep` 使用 `div onClick`，缺少 `button`、`aria-expanded`、键盘焦点和 reduced motion 兜底。
7. 沙盒入口 `?ui-canvas` 和旧 `.agent-timeline` 样式已不再属于正式产品路径。

## 修复内容

### 1. 生产页直接渲染真实 Agent Step

本轮移除了 `WorkspacePage` 对 `AgentChatPanels` mock 组件的依赖，把生产所需的轻量组件和映射逻辑收回到 `WorkspacePage.tsx`：

- `UserMessageView`
- `AgentFinalMessageView`
- `AgentStepItem`
- `AgentStepArtifact`

这样做的原因是当前交互逻辑强依赖 Workspace 本地状态，例如 `clips`、`previewSelection`、`isThinking` 和 `agentSteps`。在契约尚未完全稳定之前，把渲染逻辑保持在页面局部可以减少跨文件跳转和虚假抽象。

### 2. 真实状态优先的 step 映射

新增的映射逻辑遵循真实事件优先：

- 优先读取 `step.status`。
- 再读取 `step.details.success`。
- 最后才使用 `isThinking && isLastStep` 作为 fallback。

工具类型识别也改为优先读取 `details.tool_name`，只有缺失时才退回到 `phase` 文本启发式。

这解决了原先失败态被误显示成 success、工具 artifact 无法命中真实事件的问题。

### 3. 当前执行块的收敛逻辑

新增 `shouldShowAgentSteps`：

- 如果当前还在 thinking，展示实时 execution block。
- 如果最后一条聊天已经是 assistant final message，则收敛执行块，只保留干净的历史对话和最终决策。

这符合 `Breathing Step Flow` 的终态预期：执行细节用于当前轮次监控，历史区以最终决策为主。

### 4. 去除 mock artifact，改为真实 payload 展示

本轮删除了硬编码图片、sunset 文案和固定 patch diff。

新的 artifact 行为：

- `retrieve`：从 `details.candidate_clip_ids` 匹配当前 Workspace 的真实 clips，最多展示 4 个小卡片，点击后联动右侧播放器跳转到对应 clip。
- `inspect`：展示真实 `inspection_summary` 或 summary。
- `patch`：展示真实 `clip_id` 和 `draft_version`。
- 其他 step：展示最多 4 个真实 `details` 字段，作为轻量可观测信息。

这保证 UI 不会把 mock 数据伪装成 Agent 实际执行结果。

### 5. 交互与可访问性补强

`AgentStepItem` 改为真正的 button header：

- 使用 `aria-expanded` 表达折叠状态。
- 支持键盘焦点。
- `Manual Override` 后停止自动折叠覆盖用户选择。
- loading / success / error 三态有明确 icon 和颜色。
- 添加 `prefers-reduced-motion`，降低动画敏感用户的负担。

### 6. 沙盒脚手架清理

删除：

- `client/src/components/chat/AgentChatPanels.tsx`
- `client/src/components/chat/AgentChatPanels.css`

移除：

- `client/src/App.tsx` 中的 `?ui-canvas` 入口。
- `client/src/styles/workspace.css` 中遗留的 `.agent-timeline` / `.timeline-item` / `.timeline-empty` 样式。

## 验证结果

本轮执行并通过：

```bash
npm run typecheck
npm run build
git diff --check
```

额外做了引用扫描，确认没有残留：

- `AgentChatPanels`
- `ui-canvas`
- `chat-canvas`
- `agent-timeline`
- `timeline-empty`
- `timeline-item`

## 当前预期交互

用户发送 prompt 后：

1. 用户消息立即进入聊天历史。
2. 如果后端尚未推送具体 step，则显示简短 thinking 状态。
3. `agent.step.updated` 到达后，聊天框底部出现当前执行块。
4. 当前运行步骤自动展开，完成步骤延时折叠，失败步骤保持展开。
5. 用户手动点击某一步后，该步骤不再被自动折叠逻辑覆盖。
6. `retrieve` 结果如果能匹配真实 clips，用户可以直接点击 clip 小卡片联动右侧播放器。
7. assistant final message 到达后，执行块收敛隐藏，只保留最终决策和历史消息。

## 后续关注点

1. core 侧 `agent.step.updated` 当前仍是 append-only（只追加）语义，前端已做轻量去重，但长期最好补稳定 step id。
2. `details` payload 仍不完全结构化，后续可以把 `retrieve/inspect/patch/preview` 的 schema 固化为前后端契约。
3. 当前 artifact 展示偏实用监控面板，后续若要做更丰富的缩略图和 patch diff，需要基于真实 `clip/asset/shot` 数据继续扩展，而不是恢复 mock。
4. 建议补一轮真实 Agent 运行的手动联调，观察 planner、retrieve、inspect、patch、final message 的事件顺序是否和 UI 收敛逻辑完全一致。
