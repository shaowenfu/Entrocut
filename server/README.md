# Server Shell

`server` 当前是最小 `Cloud Orchestration Service（云端编排服务）`。

## 当前能力

1. `GET /health` 健康检查（含 `queue/storage` 状态）。
2. `POST /api/v1/index/jobs` 创建向量入库任务。
3. `POST /api/v1/chat/jobs` 创建对话编排任务。
4. `POST /api/v1/index/upsert-clips` 同步等待入库完成（兼容模式）。
5. `POST /api/v1/chat` 同步返回 `AgentDecision`。
6. `GET /api/v1/jobs/{job_id}` 查询任务状态。
7. `POST /api/v1/jobs/{job_id}/retry` 手动重试失败任务。

## 说明

## 环境变量

1. `AUTH_JWT_SECRET`：`JWT` 校验密钥（必填）。
2. `AUTH_JWT_ALGORITHM`：默认 `HS256`。
3. `REDIS_URL`：外部队列地址。
4. `SERVER_DB_PATH`：`SQLite` 文件路径。

## 说明

1. `chat` 响应已升级为结构化 `project/patch/ops`。
2. 所有业务接口都需要 `Authorization: Bearer <token>`。
3. 错误统一返回 `ErrorEnvelope`。
