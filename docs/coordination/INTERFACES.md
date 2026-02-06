# Interfaces（契约索引）

## Schema（结构）
- `docs/schemas/analysis.json`（Qwen3-VL 输出结构）
- 变更流程：先更新 `CHANGE_LOG.md` → 修改 Schema（结构）→ 通知相关 Agent（代理）

## API（接口）
- `server` 使用 OpenAPI（接口规范）文档对齐（FastAPI 自带 `/docs`）
- 任何 API（接口）变更必须记录到 `CHANGE_LOG.md`

## Local RPC（本地远程过程调用）
- `client` → `core` 使用 JSON-RPC（JSON 远程过程调用）
- 变更需同步更新 `CHANGE_LOG.md` 与对应实现

## Contract-First（契约优先）原则
- Schema（结构）与 API（接口）是 SSOT（单一事实源）
- 任何实现变更不得绕过契约变更流程
