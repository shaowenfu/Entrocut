# Server Shell

`server` 当前是最小 `Cloud Orchestration Shell（云端编排壳层）`。

## 当前能力

1. `GET /health` 健康检查。
2. `POST /api/v1/index/upsert-clips` 最小向量化写入确认。
3. `POST /api/v1/chat` 返回 `AgentDecision`（用于工作台分镜更新与澄清提示）。

## 说明

旧 `Mock API`、旧路由组、旧中间件和旧测试已全部移除。
