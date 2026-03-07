# Core Skeleton

`core` 已进入 `clean-room rewrite（净室重构）` 阶段。

## 当前定位

`core` 现在只保留最小 `FastAPI（服务框架）` 壳，用来承接下一轮从零重建的本地工作流。

## 当前能力

1. `GET /health`
2. `GET /api/v1/runtime/capabilities`
3. `GET /`

## 非目标

当前版本 **不包含**：

1. `project management（项目管理）`
2. `ingest（素材处理）`
3. `chat orchestration（对话编排）`
4. `search（检索）`
5. `render（渲染）`
6. `WebSocket event stream（事件流）`

## 保留原因

1. 保留本地服务启动方式
2. 保留 `request_id（请求标识）` 中间件
3. 保留本地 `CORS（跨域）` 访问支持
4. 为下一轮重新定义 `schema（契约）` 提供干净落点
