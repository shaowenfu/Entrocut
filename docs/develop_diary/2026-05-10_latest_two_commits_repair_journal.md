# 2026-05-10 最新两个提交排查与修复日记

今天的工作不是继续堆新功能，而是把最新两个提交真正并入现有系统契约。

这两个提交的方向本身是合理的：

1. `da78137 feat: 实现启动台项目删除与视频播放器 Bug 修复`
2. `3892e70 增加提问功能`

问题在于实现只覆盖了局部代码路径，没有把 `core`、`client`、状态模型、事件流和测试一起闭合。结果是功能看上去已经接入，实际在运行时会出现启动失败、UI 无法展示新消息类型、暂停任务无法恢复等问题。

## 1. 项目删除与播放器修复提交

第一个提交的出发点有两个。

一是让 `Launchpad（启动台）` 支持删除完整项目。实现上在 `client` 增加删除按钮和 `deleteProject` store action，在 `core` 增加 `DELETE /api/v1/projects/{project_id}`，后端删除内存记录、`SQLite（嵌入式数据库）` 记录和本地 workspace 目录。

二是修视频播放器在切换素材、clip 和 scene 时的播放问题。实现上把播放触发从 `isPlaying` 状态驱动改成更多直接调用 `video.play()`，并通过 `requestAnimationFrame` 延后到下一帧，避免 video 元素或 source 尚未切换完成时播放失败。

这次排查发现的关键问题是：

1. 删除接口声明为 `204`，但 `FastAPI（Web 框架）` 仍推断有 response body（响应体），导致应用在导入路由阶段直接失败。
2. 删除功能没有测试覆盖，无法证明数据库级联删除和 workspace 目录删除都生效。
3. 播放器修改改变了原有 `isPlaying` 状态语义，虽然解决了一类时序问题，但也让播放失败被吞掉，后续仍需要人工端到端检查。

本轮修复先收敛项目删除的硬错误：删除接口显式返回空 `Response`，并补了 integration test（集成测试）覆盖 `204` 空响应、项目记录删除、workspace 目录删除和删除后的 `404`。

## 2. Agent 提问功能提交

第二个提交的目标是让 `Agent（智能体）` 在信息不足时可以进入 `ask_user` 状态，而不是硬猜用户意图。

原提交完成了这些基础工作：

1. 在 `PlannerDecisionModel（规划决策模型）` 中增加 `ask_user`。
2. 在 `Prompt（提示词）` 输出契约中说明 `question/options/allow_custom/context_brief`。
3. 在 agent loop（智能体循环）中识别 `ask_user` 并返回。
4. 在 store 中把问题写入 `chat_turns`，并把 task（任务）标记为 `paused`。
5. 写了 `docs/agent_runtime/18_agent_question.md` 作为设计说明。

这个方向是对的，因为剪辑决策里确实有很多不能由模型独断的选择：风格、节奏、受众、是否允许偏离原素材叙事等。但原实现只做到了“后端能生成问题”，没有完成“用户能看到问题、回答问题、系统能继续执行”的闭环。

排查后确认的缺口包括：

1. `client` 的 `CoreChatTurn` 仍只认识普通 user turn 和 assistant decision turn，无法表达 question turn 和 answer turn。
2. `WorkspacePage` 把所有 assistant turn 都强转为 decision turn，导致 question turn 只会显示成默认完成文案。
3. 前端 `TaskStatus` 不包含 `paused`，实时事件里 paused task 会被丢弃，snapshot 又可能带回来，状态语义不稳定。
4. 没有 answer API（回答接口），用户无法把选项提交回 `core`。
5. 后端没有在用户回答后消费 paused task，也没有清理 `pending_questions`。

本轮修复把这个闭环补齐：

1. `core` 新增 `ChatAnswerRequest` 和 `POST /api/v1/projects/{project_id}/questions/{question_id}:answer`。
2. `AgentAskTurnModel` 增加 `question_id` 和 `allow_custom`，让问题 turn 有稳定业务 ID。
3. store 新增 `answer_agent_question`：校验问题和选项，写入 `UserAnswerTurnModel`，移除 paused agent task，再启动新的 chat task 继续规划。
4. `render_chat_history` 能把 question/answer 历史渲染回下一轮 `Prompt`，避免模型丢上下文。
5. `client` 补齐 `paused`、question turn、answer turn 类型。
6. `WorkspacePage` 增加问题卡片，展示 2-4 个选项和自定义回答输入，并通过 answer API 继续对话。
7. 新增测试覆盖 `ask_user -> paused -> answer -> final` 的完整链路。

这里我没有选择“把原后台 coroutine 挂起并恢复”。原因是现有系统的任务模型本来就是短生命周期 task：HTTP 请求触发后台任务，任务完成后通过事件和持久化状态推进 UI。让一个 coroutine 跨用户等待长期存活，会把恢复、重启、取消和持久化都变复杂。更简单稳定的做法是：`ask_user` 结束当前任务并留下问题；用户回答后创建新任务继续执行，同时把 answer turn 作为上下文事实写入历史。

## 3. 本轮验证

本轮已经运行：

1. `client`: `npm run typecheck`
2. `core`: `source venv/bin/activate && python -m pytest tests/test_context_engineering.py tests/test_server_toolchain_integration.py -q`
3. 新增两个针对性测试：
   - `test_chat_can_ask_user_and_resume_from_answer`
   - `test_delete_project_removes_records_and_workspace`

后续仍建议手动跑一次桌面端：

1. 在 `Launchpad（启动台）` 删除项目，确认列表、工作区目录和错误提示都符合预期。
2. 触发一次需要澄清的问题，确认选项点击、自定义回答、继续规划和聊天历史展示都符合预期。
3. 检查播放器在素材处理中、clip 切换、scene 切换三种路径下是否有产品层面的限制遗漏。

## 4. 这次给后续留下的边界

`ask_user` 现在是一个完整但克制的闭环：问题、回答、继续执行都进入了契约，但没有引入复杂的长期任务恢复模型。

项目删除现在是后端可验证能力，但前端仍是轻量确认框。后续如果要支持“从打开的 Workspace 删除当前项目”或“多端同时打开同一项目”，再补 `project.deleted` event（项目删除事件）和自动回到 Launchpad 的 UI 状态机。

播放器修改这次没有扩大重构。它属于交互时序问题，适合在真实视频素材和 Electron（桌面壳）里继续做人工验证，而不是用当前修复任务顺手重写整块播放状态机。
