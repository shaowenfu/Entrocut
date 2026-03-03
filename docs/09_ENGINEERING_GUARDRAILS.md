# 09. Engineering Guardrails（工程护栏）

本文件合并 `Observability（可观测性）`、`Privacy（隐私）`、`Error Semantics（错误语义）`、`Non-goals（非目标）`、`Decisions（关键决策）`。

## 1. 可观测性基线

## 1.1 Logging（日志）

关键字段：

1. `request_id`
2. `user_id`
3. `project_id`
4. `session_id`
5. `endpoint`
6. `latency_ms`
7. `error_code`

要求：

1. `core/server` 统一输出结构化 `JSON Log`。
2. 客户端错误提示需附带 `request_id`，支持跨端排障。

## 1.2 Metrics（指标）

MVP 必备：

1. `ingest_latency_ms`
2. `vector_upsert_latency_ms`
3. `retrieval_latency_ms`
4. `chat_latency_ms`
5. `render_start_latency_ms`
6. `export_success_rate`

## 1.3 Trace（链路追踪）

1. `client` 发起请求生成 `request_id`。
2. `core/server` 透传 `request_id`。
3. 多轮对话通过 `session_id` 聚合。

## 2. 隐私与数据边界

1. 原始视频不上传云端。
2. 云端只保留向量和最小元数据：`user_id/file_path/time_range`。
3. 每次检索强制追加 `user_id` 过滤。
4. 禁止日志打印完整 `Base64` 与敏感凭证。

## 3. 错误语义

统一错误结构：

```json
{
  "error": {
    "code": "CORE_RENDER_FAILED",
    "message": "Render preview failed.",
    "details": {
      "request_id": "req_001",
      "retryable": true
    }
  }
}
```

规则：

1. 错误码必须可枚举、可分支处理。
2. `4xx` 代表输入/权限/状态问题，`5xx` 代表服务失败。
3. `message` 对外稳定可读，禁止暴露内部实现细节。
4. 禁止吞错与静默降级。

## 4. 非目标（MVP）

当前不做：

1. 完整 `NLE Timeline（专业非线性时间线）` 能力。
2. `Undo/Redo（撤销/重做）` 与快捷键系统。
3. 多用户实时协作。
4. 云端原始素材托管。
5. 高级调色、复杂转场、关键帧动画、字幕系统。
6. 完整 `Agent Tool/Skill Runtime（智能体工具/技能运行时）`。
7. 多导出预设与批量导出。

## 5. 当前关键决策（冻结）

1. 主路径是 `Chat-to-Cut`，不是编辑器优先。
2. 架构采用 `Hybrid Local-First`。
3. `server` 仅对外暴露单一 `POST /api/v1/chat` 作为 `Agent` 入口。
4. `EntroVideoProject` 是三端共享契约。
5. `Timeline` 在 MVP 不引入状态机，按最新契约覆盖。
6. 导出仅默认配置，导出期间禁止并行编辑。
7. 素材检索粒度为 `AtomicClip（切片级）`。
8. `reasoning` 为必填可视解释字段。

## 6. 保留扩展位（不实现）

1. `Multi-User Interface（多用户接口）` 字段保留。
2. `Agent Tool/Skill` 调用框架字段保留。
3. `AI Quick Start` 入口保留。
