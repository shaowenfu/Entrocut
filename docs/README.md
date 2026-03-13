# Docs 导航

`docs/` 现在按开发方向分组，优先服务当前仍在推进的主线，避免不同主题的文档继续平铺在根目录。

## 推荐入口

1. 想先理解整体文档布局，看当前页。
2. 想看剪辑基础模型，从 [editing/README.md](./editing/README.md) 开始。
3. 想系统看 `editing agent（剪辑智能体）` 设计，按 [agent_runtime/README.md](./agent_runtime/README.md) 的顺序阅读。
4. 想看 `client -> core` 本地契约，从 [contracts/README.md](./contracts/README.md) 开始。
5. 想看 `server` 方向的设计与约束，从 [server/README.md](./server/README.md) 开始。
6. 想回顾推进过程，直接看 [develop_diary](./develop_diary/)。

## 目录分组

### 1. Contracts（契约）

- [contracts/README.md](./contracts/README.md)
- 当前重点：
  - [Core API / WS Contract](./contracts/01_core_api_ws_contract.md)

### 2. Editing（剪辑基础）

- [editing/README.md](./editing/README.md)
- 当前重点：
  - [EditDraft Schema](./editing/01_edit_draft_schema.md)

### 3. Agent Runtime（智能体运行时）

- [agent_runtime/README.md](./agent_runtime/README.md)
- 这一组文档已经按推荐阅读顺序编号，建议直接按文件名前缀阅读。

### 4. Server（服务端）

- [server/README.md](./server/README.md)
- 包含：
  - 模块设计
  - 接口面
  - 鉴权
  - `OpenAI-compatible` 契约
  - `RAG / Vector`
  - 生产加固与 `staging` 运行说明

### 5. Develop Diary（开发日记）

1. [2026-03-07 重建日记](./develop_diary/2026-03-07_rebuild_journal.md)
2. [2026-03-08 EditDraft Contract 落地日记](./develop_diary/2026-03-08_edit_draft_contract_landing_journal.md)
3. [2026-03-09 Server 鉴权与桌面登录回流日记](./develop_diary/2026-03-09_server_auth_and_desktop_login_journal.md)
4. [2026-03-09 Agent Runtime Notes](./develop_diary/2026-03-09_agent_runtime_notes.md)
5. [2026-03-13 Agent Runtime 落地开发日志](./develop_diary/2026-03-13_agent_runtime_landing_journal.md)

### 6. Reference / Archive / Secrets

- [reference/](./reference/)
- [archive/README.md](./archive/README.md)
- [secrets/](./secrets/)

## 当前推荐阅读路径

如果目标是快速进入当前主线，建议按这个顺序：

1. [editing/01_edit_draft_schema.md](./editing/01_edit_draft_schema.md)
2. [contracts/01_core_api_ws_contract.md](./contracts/01_core_api_ws_contract.md)
3. [agent_runtime/README.md](./agent_runtime/README.md)
4. [develop_diary/2026-03-13_agent_runtime_landing_journal.md](./develop_diary/2026-03-13_agent_runtime_landing_journal.md)
