# Baseline Architecture

## 1. 结构

```text
Entrocut/
  client/  # UI Shell（界面壳层）
  core/    # Local Service Shell（本地服务壳层）
  server/  # Cloud Orchestration Shell（云端编排壳层）
  docs/    # Baseline Docs（基线文档）
```

## 2. 职责边界

1. `client`：仅负责页面壳层与进程边界占位，不包含业务编排逻辑。
2. `core`：仅暴露本地能力入口占位（`ingest/search/render`），当前不实现算法。
3. `server`：仅暴露编排入口占位（`chat`），当前不实现 Agent（智能体）逻辑。

## 3. 设计原则

1. `Schema-First（结构优先）`：先定义契约，再写实现。
2. `KISS（简洁原则）`：不保留历史验证代码，不提前实现未来功能。
3. `Single Direction Dependency（单向依赖）`：`client -> core/server`，禁止反向耦合。
