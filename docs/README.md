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

## 历史归档

1. [Archive](./archive/README.md)
   - 存放阶段性中间文档
   - 当前已归档“重建阶段”的状态模型、联调跟进等文档
