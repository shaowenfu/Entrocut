# EntroCut Contract v0.1（契约）

## 0. 原则
- v0.1 仅覆盖本地编辑框架与导出。
- 预留 Multi-User（多用户）接口位（userId），不实现权限。
- AI Tool（工具）/Skill（技能）调用仅占位，禁止驱动 Timeline（时间线）。

## 1. Client（客户端）<-> Core（本地算法）

### 1.1 `POST /jobs/start`
- 用途：启动渲染任务（Export（导出））。
- Request：
1. projectId（字符串）
2. timeline（Timeline（时间线）结构）
3. outputName（字符串，可选）
- Response：
1. taskId（字符串）
2. status（queued）

### 1.2 `GET /jobs/{taskId}`
- 用途：查询渲染任务状态。
- Response：
1. taskId（字符串）
2. status（queued|rendering|success|failed）
3. outputPath（字符串，可选）
4. error（错误对象，可选）

### 1.3 `POST /jobs/{taskId}/cancel`
- 用途：取消渲染任务。
- Response：
1. taskId（字符串）
2. status（failed）

## 2. Client（客户端）<-> Server（云端）

### 2.1 `POST /ai/chat`
- 用途：AI Copilot（AI 副驾驶）对话（仅文本）。
- Request：
1. sessionId（字符串）
2. projectId（字符串）
3. messages（消息数组）
- Response：
1. message（assistant 消息）

## 3. 错误语义（Error Semantics（错误语义））
- 统一结构：
```
{
  "error": {
    "type": "validation_error|runtime_error|external_error",
    "code": "ENUM_CODE",
    "message": "readable message",
    "details": {}
  }
}
```

## 4. 版本治理（Versioning（版本治理））
- v0.1 不冻结 Schema（结构），但字段不可任意改名。
- v1.0 起冻结 Contract（契约）并启用严格版本号。
