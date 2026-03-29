# 2026-03-09 Agent Runtime Notes

- 这轮讨论开始明显从“局部契约设计”切到“agent 整体运行方式”。
- 先前几轮聚焦的是：
  - `Storyboard` 为什么不应是事实源
  - `EditDraft` 为什么必要
  - `clip / shot / scene` 如何分层
  - 为什么 `shot` 是最小可编辑语义单元
  - 为什么系统必须走 `retrieval-first` 路线
- 这些讨论本身没有错，它们更像在给 `agent` 的 `world model` 和执行层打地基。

- 今天用户明确提出一个关键视角：
  - 不能只盯着局部 schema 和执行细节
  - 要回到主流 `agent` 的整体设计视角
  - 但也不能照着通用模板机械堆砌

- 当前新的共识：
  - `editing agent` 应按五层来理解：
    - `State`
    - `Planner`
    - `Tool`
    - `Memory / Context`
    - `Execution Loop`
  - 这五层不是教科书，而是后续逐层落地的骨架

- 对“为什么之前没直接按五层开始设计”的反思：
  - 不是单纯提示词误导
  - 更本质的原因是，当时的问题天然集中在：
    - `scene` 有没有必要
    - `Storyboard` 的角色是什么
    - `EditDraft schema` 如何定义
    - 检索和 patch 应该怎样表达
  - 这些问题会把讨论先拉到：
    - 世界模型
    - 执行对象
    - 契约边界
  - 这其实是正常顺序，不算走偏

- 关键认知更新：
  - `selection_context -> retrieval_request -> candidate clips -> edit_draft_patch`
    不能被理解成整个 `agent` 的总流程
  - 它更准确地说，是：
    - 当 `agent` 决定执行一次“面向草案的具体修改”时的最小执行路径
  - 外层仍应保持开放对话
  - 中层应是一个较薄的规划层
  - 内层才进入结构化执行链

- 关于规划层：
  - 不应写成枚举所有用户话术的大量 `if-else`
  - 更合理的思路是：
    - 不枚举用户会怎么说
    - 只枚举系统下一步可以做什么动作
  - 这直接催生出 `planner actions` 的讨论

- 当前已经收敛出的 `planner actions`：
  - `reply_only`
  - `ask_clarification`
  - `update_goal`
  - `set_selection_context`
  - `create_retrieval_request`
  - `inspect_candidates`
  - `apply_patch`
  - `render_preview`

- 对上下文工程的再理解：
  - 不能把它只理解成“prompt 塞上下文”
  - 更准确的是：
    - `session runtime state`
  - 它至少包含：
    - `conversation context`
    - `working context`
    - `execution history`
    - `task/session plan`

- 一个重要共识：
  - 会过时的是：
    - 话术分类器
    - 过度具体的 prompt 流程编排
    - 模拟模型思维的僵硬状态机
  - 不会过时的是：
    - 世界模型
    - 工具契约
    - patch 结构
    - 上下文状态边界
    - 错误语义

- 这意味着：
  - 接下来不应优先写复杂规划框架
  - 而应先把 `agent runtime` 的总架构和每层职责钉住

- 今天新增动作：
  - 新建 `docs/agent_runtime/02_editing_agent_runtime_architecture.md`
  - 作为后续逐层细化的方向性骨架文档

- 当前建议的后续顺序：
  - 先设计 `State Layer`
  - 再设计 `Planner Layer`
  - 然后补执行层契约
  - 再设计 `Memory / Context`
  - 最后把 `Execution Loop` 串起来

- 留待后续继续补的点：
  - `session runtime state` 到底放哪些字段
  - `planner action schema` 怎么落
  - `retrieval_request / selection_context / edit_draft_patch` 与 runtime state 怎么对齐
  - 上下文裁剪策略怎么设计
