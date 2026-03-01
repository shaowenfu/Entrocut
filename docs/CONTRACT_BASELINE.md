# Contract Baseline

## 1. Core API（本地服务）

1. `GET /health`
2. `POST /api/v1/ingest`（Placeholder（占位））
3. `POST /api/v1/search`（Placeholder（占位））
4. `POST /api/v1/render`（Placeholder（占位））

## 2. Server API（云端服务）

1. `GET /health`
2. `POST /api/v1/chat`（Placeholder（占位））

## 3. 统一错误语义

占位接口统一返回 `501`，`detail` 结构固定：

```json
{
  "code": "NOT_IMPLEMENTED",
  "message": "Feature is not implemented in baseline."
}
```
