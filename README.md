# EntroCut Monorepo

`EntroCut` 当前进入 `MVP` 重构阶段，目标是交付 `Chat-to-Cut（对话生成剪辑）` 闭环。

当前已接入以下全局基线：

1. `JWT Auth（鉴权）`：`core/server` 强制校验 `Authorization: Bearer <token>`。
2. `ErrorEnvelope（统一错误包）`：三端按 `error.code/error.message/error.details` 对齐。
3. `Redis Queue（外部队列）`：`ingest/index/chat` 统一基于 `job` 模型执行。
4. `SQLite Persistence（持久化）`：`core/server` 重启后数据可恢复。
5. `request_id` 贯通：前端请求自动注入 `X-Request-ID`，后端回传并记录。

## 目录结构

1. `client/`：`Electron + React` 客户端壳层，承载 `AI Copilot` 界面与状态同步。
2. `core/`：本地 `Python Sidecar`，负责切分、抽帧、渲染与导出。
3. `server/`：云端 `FastAPI`，负责 `Agent` 编排、向量化与会话管理。
4. `docs/`：MVP 设计与开发文档集（当前唯一规范源）。

## MVP 主路径

1. `Ingest`：本地素材导入、切分、关键帧拼图与向量索引。
2. `Agent`：通过单一 `POST /api/v1/chat` 处理所有自然语言交互。
3. `EditDraft`：在 `Asset / Clip / Shot / Scene` 分层上形成结构化剪辑草案。
4. `Render`：以 `EditDraft.shots` 为最终执行输入生成可预览结果。

## API 入口（当前规范）

1. `core`（本地）：
   1. `GET /health`
   2. `GET /api/v1/projects`
   3. `GET /api/v1/projects/{project_id}`
   4. `POST /api/v1/projects`
   5. `POST /api/v1/projects/import`
   6. `POST /api/v1/projects/upload`
   7. `POST /api/v1/projects/{project_id}/assets/import`
   8. `POST /api/v1/projects/{project_id}/assets/upload`
   9. `POST /api/v1/ingest`
   10. `POST /api/v1/search`
   11. `POST /api/v1/render`
2. `server`（云端）：
   1. `GET /health`
   2. `POST /api/v1/index/upsert-clips`
   3. `POST /api/v1/chat`（唯一 `Agent` 对外入口）

详细契约见 `docs/`：

1. `docs/contracts/01_core_api_ws_contract.md`
2. `docs/editing/01_edit_draft_schema.md`

## 快速启动

1. 一键启动本地三端（推荐）

```bash
./scripts/dev_up.sh
```

2. 生成开发 Token（本地）

```bash
AUTH_JWT_SECRET=entrocut-dev-secret-change-me ./scripts/issue_dev_token.sh
```

将输出的 token 写入 `client/.env`：

```bash
VITE_AUTH_TOKEN=<your_token>
```

3. 运行冒烟测试（Auth + Queue + Contract）

```bash
bash scripts/smoke_test.sh
```

4. 手动启动 `client`

```bash
cd client
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

5. 手动启动 `core`

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

6. 手动启动 `server`

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## 当前实现状态

1. 启动台主路径已接入真实项目接口；其余核心能力仍以 `Shell（壳层）` 为主。
2. 当前剪辑结构设计以 `docs/editing/01_edit_draft_schema.md` 为准：
   - `clip` 是分析/检索单元
   - `shot` 是最小可编辑语义单元
   - `scene` 是可选工作分组层
   - `render` 以 `shots` 为准，而不是以展示型 `storyboard` 为准
3. 历史验证阶段代码和过时文档已清理。
