# Contracts 文档

这一组文档描述当前 `client / core` 之间已经收敛下来的本地契约。

## 当前文档

1. [Core API / WS Contract](./01_core_api_ws_contract.md)
   - 当前前端与本地 `Core` 之间的真实公开契约
   - 包含资源模型、`HTTP API`、`WebSocket event stream` 和错误语义
   - 剪辑结构部分统一引用 `EditDraft Schema`
2. [Local Data Storage Architecture](./02_local_data_storage_architecture.md)
   - 定义桌面端 `SQLite + File System + Keychain/Credential Manager` 与云端 `MongoDB Atlas` 的职责边界
3. [Local Data Storage Refactor Plan](./03_local_data_storage_refactor_plan.md)
   - 把本地数据层架构原则落成可执行的改造方案，覆盖 `SQLite`、项目工作目录、素材引用和凭证迁移
   - 其中涉及 `workflow_state` 的内容应理解为存储层兼容信息，不代表当前公开 API
4. [Project State Management Refactor Design](./04_project_state_management_refactor_design.md)
   - 从第一性原理重构 `Project / Asset / EditDraft / Runtime / Task` 的状态归属与派生 capability 设计
   - 当前主要作为设计背景与迁移决策记录，最新契约仍以 `01` 为准

## 2026-04 导入链路补充口径

与 `real_desktop_ingest_retrieval` 任务一致，当前契约补充如下：

1. `create_project` 只负责创建空项目与空草稿
2. 真实素材必须通过 `assets:import` + `media.files[]` 导入
3. `media.files[*].path` 必须是绝对本地文件路径
4. `folder_path` 不再作为真实 ingest 输入，仅可作为上游扫描描述

## 当前阅读原则

1. 想看“现在代码到底怎么对外表达”，先读 [01_core_api_ws_contract.md](./01_core_api_ws_contract.md)
2. 想看“为什么会变成现在这样”，再读 [04_project_state_management_refactor_design.md](./04_project_state_management_refactor_design.md)
3. 想看“本地持久化为什么还保留某些兼容字段”，再读 [03_local_data_storage_refactor_plan.md](./03_local_data_storage_refactor_plan.md)

## 推荐阅读顺序

1. 先看 [editing/01_edit_draft_schema.md](../editing/01_edit_draft_schema.md)
2. 再看 [01_core_api_ws_contract.md](./01_core_api_ws_contract.md)
3. 再看 [02_local_data_storage_architecture.md](./02_local_data_storage_architecture.md)
4. 再看 [03_local_data_storage_refactor_plan.md](./03_local_data_storage_refactor_plan.md)
5. 最后看 [04_project_state_management_refactor_design.md](./04_project_state_management_refactor_design.md)
