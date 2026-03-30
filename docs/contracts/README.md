# Contracts 文档

这一组文档描述当前 `client / core` 之间已经收敛下来的本地契约。

## 当前文档

1. [Core API / WS Contract](./01_core_api_ws_contract.md)
   - 当前前端与本地 `Core` 之间的最小契约
   - 包含资源模型、`HTTP API`、`WebSocket event stream` 和错误语义
   - 剪辑结构部分统一引用 `EditDraft Schema`
2. [Local Data Storage Architecture](./02_local_data_storage_architecture.md)
   - 定义桌面端 `SQLite + File System + Keychain/Credential Manager` 与云端 `MongoDB Atlas` 的职责边界

## 推荐阅读顺序

1. 先看 [editing/01_edit_draft_schema.md](../editing/01_edit_draft_schema.md)
2. 再看 [01_core_api_ws_contract.md](./01_core_api_ws_contract.md)
3. 最后看 [02_local_data_storage_architecture.md](./02_local_data_storage_architecture.md)
