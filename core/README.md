# Core Shell

`core` 当前是最小 `Local Service（本地核心服务）`。

## 当前能力

1. `GET /health` 健康检查（含 `queue/storage` 状态）。
2. `GET /api/v1/projects` 项目列表（Launchpad 数据源）。
3. `POST /api/v1/projects` 创建空项目/带素材路径项目。
4. `POST /api/v1/projects/import` 通过本地目录导入并创建项目。
5. `POST /api/v1/projects/upload` 通过浏览器上传视频并创建项目。
6. `GET /api/v1/projects/{project_id}` 工作台读取项目详情（assets/clips）。
7. `POST /api/v1/projects/{project_id}/assets/import` 工作台追加目录素材。
8. `POST /api/v1/projects/{project_id}/assets/upload` 工作台追加上传素材。
9. `POST /api/v1/ingest/jobs` 创建异步切分任务。
10. `POST /api/v1/ingest` 同步等待切分完成（兼容模式）。
11. `GET /api/v1/jobs/{job_id}` 查询任务状态。
12. `POST /api/v1/jobs/{job_id}/retry` 手动重试失败任务。
13. `POST /api/v1/search` 占位。
14. `POST /api/v1/render` 占位。

## 说明

## 环境变量

1. `AUTH_JWT_SECRET`：`JWT` 校验密钥（必填）。
2. `AUTH_JWT_ALGORITHM`：默认 `HS256`。
3. `REDIS_URL`：外部队列地址。
4. `CORE_DB_PATH`：`SQLite` 文件路径。

## 说明

1. 所有业务接口都需要 `Authorization: Bearer <token>`。
2. 错误统一返回 `ErrorEnvelope`。
3. `ingest` 不做自动重试，失败后仅支持手动重试。
