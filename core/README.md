# Core Shell

`core` 当前是最小 `Local Service Shell（本地服务壳层）`。

## 当前能力

1. `GET /health` 健康检查。
2. `GET /api/v1/projects` 项目列表（Launchpad 数据源）。
3. `POST /api/v1/projects` 创建空项目/带素材路径项目。
4. `POST /api/v1/projects/import` 通过本地目录导入并创建项目。
5. `POST /api/v1/projects/upload` 通过浏览器上传视频并创建项目。
6. `GET /api/v1/projects/{project_id}` 工作台读取项目详情（assets/clips）。
7. `POST /api/v1/projects/{project_id}/assets/import` 工作台追加目录素材。
8. `POST /api/v1/projects/{project_id}/assets/upload` 工作台追加上传素材。
9. `POST /api/v1/ingest` 最小切分能力（按 `project_id` 产出 clips）。
10. `POST /api/v1/search` 占位。
11. `POST /api/v1/render` 占位。

## 说明

旧 `Pipeline（管线）` 代码（切分、抽帧、渲染、Mock 客户端）已全部清理。
