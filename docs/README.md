# Docs 导航

这个目录只保留当前阶段仍直接服务开发的主文档，以及历史归档入口。

## 当前主文档

1. [Core API / WS Contract](./core_api_ws_contract.md)
   - 当前前端与本地 `Core` 之间的最小契约
   - 已按 `EditDraft schema` 修正剪辑结构相关表述
   - 包含资源模型、`HTTP API`、`WebSocket event stream` 和错误语义
2. [Server Auth System Design](./server_auth_system_design.md)
   - 当前 `server` 的登录、注册、用户管理、`OAuth`、`JWT`、桌面回调完整方案
   - 基于 `MongoDB Atlas + Redis + FastAPI`
   - 说明用户模型、会话模型、接口面、运行配置与分阶段实施计划
3. [Server OpenAI-Compatible Contract](./server_openai_compatible_contract.md)
   - 当前 `Core -> Server` 的最小云端通信契约
   - 以 `OpenAI-compatible` 为第一原则
   - 包含 `chat completions`、`SSE`、`usage`、`entro_metadata` 和错误语义
4. [Auth Implementation Spec](./auth_implementation_spec.md)
   - 当前已落地的 `client / core / server` 鉴权实现规范
   - 面向工程接入，聚焦 token 生命周期、字段边界、错误语义与职责分工
4. [EditDraft Schema](./edit_draft_schema.md)
   - 当前推荐的剪辑草案结构定义
   - 说明 `Asset / Clip / Shot / Scene / EditDraft` 的分层原则与边界
5. [Editing Agent 详细设计](./editing_agent_design_detailed.md)
   - 汇总近期关于 `editing agent` 的高密度讨论
   - 详细说明设计原则、关键难点、检索路线与工程取舍
6. [Editing Agent 开发指南](./editing_agent_dev_guide.md)
   - 面向接下来实现阶段的精简指导文档
   - 聚焦分层、边界、优先级与近期落地路径
7. [Editing Agent Runtime Architecture](./editing_agent_runtime_architecture.md)
   - 当前 `editing agent` 的方向性五层运行时架构
   - 只定义整体骨架与层间关系，暂不展开具体实现细节
8. [State Layer Design](./state_layer_design.md)
   - 从 `chat-to-cut` 第一性原理推导当前所需运行时状态
   - 定义 `Goal / Draft / Selection / Retrieval / Execution / Conversation` 六类状态边界
9. [Planner Action Schema](./planner_action_schema.md)
   - 定义 `Planner Layer` 当前推荐的 8 类动作与动作边界
   - 说明它如何把 `runtimeState -> planner -> tool -> runtimeState` 串成最小闭环
10. [Tool Layer Minimal Contract](./tool_layer_minimal_contract.md)
   - 定义当前阶段 `read / retrieve / inspect / patch / preview` 五类最小工具契约
   - 说明高层工具与底层检索、多模态、`ffmpeg` 能力的分层关系
11. [Read Tool Contract](./read_tool_contract.md)
   - 定义 `read` 工具的字段级输入输出与错误语义
   - 约束它只读取当前工作事实，而不是全量数据库
12. [Retrieval Request Schema](./retrieval_request_schema.md)
   - 定义 `retrieve` 工具的字段级请求与响应结构
   - 约束检索请求必须同时表达查询、约束、偏好和召回策略
13. [Inspect Tool Contract](./inspect_tool_contract.md)
   - 定义 `inspect` 工具的字段级输入输出与错误语义
   - 用于候选比较、重排、消歧和深视觉判断
14. [EditDraft Patch Schema](./edit_draft_patch_schema.md)
   - 定义 `patch` 工具的字段级操作集合、补丁结构与错误语义
   - 明确 `EditDraftPatch` 是 agent 的标准执行输出
15. [Preview Tool Contract](./preview_tool_contract.md)
   - 定义 `preview` 工具的字段级输入输出与错误语义
   - 明确预览是草案审阅输出，不是最终导出
16. [Memory / Context Layer Design](./memory_context_layer_design.md)
   - 定义 `Memory / Context Layer` 的第一性原理、工程实体与最佳实践
   - 说明 `ActionContextPacket`、`Context Assembler` 以及上下文裁剪/回写原则
17. [ActionContextPacket Schema](./action_context_packet_schema.md)
   - 定义 `ActionContextPacket` 的本质、设计原则与推荐最小结构
   - 强调它是按当前动作裁剪出的最小决策上下文包
18. [Context Assembler Design](./context_assembler_design.md)
   - 定义 `Context Assembler` 的职责、输入输出、装配流程与裁剪规则
   - 说明它如何把 `runtimeState` 装配成 `ActionContextPacket`
19. [Planner Output Schema](./planner_output_schema.md)
   - 定义 `planner` 对外的结构化决议输出
   - 说明它如何与状态更新、工具调用和执行闭环对齐
20. [Execution Loop Design](./execution_loop_design.md)
   - 定义 `Execution Loop` 的最小执行阶段、继续/停止条件和失败语义
   - 说明它如何把状态、上下文、决议、工具执行与回写串成运行闭环

## 开发日记

1. [2026-03-07 重建日记](./develop_diary/2026-03-07_rebuild_journal.md)
   - 记录从“清场式重构”到“最小闭环跑通”的完整推进过程
   - 包含目标、动机、做法、联调结果和反思
2. [2026-03-09 Server 鉴权与桌面登录回流日记](./develop_diary/2026-03-09_server_auth_and_desktop_login_journal.md)
   - 记录 `server auth phase 1`、`Google OAuth`、`JWT`、`Electron deep link` 和 `web dev fallback` 的完整落地过程
   - 包含架构取舍、联调问题与最终修正点
3. [2026-03-09 Agent Runtime Notes](./develop_diary/2026-03-09_agent_runtime_notes.md)
   - 记录从局部剪辑契约讨论切换到五层 `agent runtime` 设计的思考过程
   - 用于后续继续补充 `planner / state / context / loop` 相关设计笔记
4. [2026-03-13 Agent Runtime 落地开发日志](./develop_diary/2026-03-13_agent_runtime_landing_journal.md)
   - 以第一人称详细回顾本轮 session 中从五层架构讨论到运行时骨架代码化的完整推进过程
   - 重点记录 `state / context / planner / tool / execution loop` 的动机、设计与落地路径

## 历史归档

1. [Archive](./archive/README.md)
   - 存放阶段性中间文档
   - 当前已归档“重建阶段”的状态模型、联调跟进等文档
