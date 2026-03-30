# 拆分 core/server.py 为多模块结构

## Context

`core/server.py` 当前约 1781 行，包含 FastAPI app 创建、配置、数据模型、工具函数、Agent 循环、Store 类、API 路由等所有逻辑。需要按 FastAPI 最佳实践拆分为独立模块，便于维护和阅读。

**约束**：不改变任何业务逻辑，只做文件搬迁和 import 调整。

## 目标目录结构

```
core/
├── server.py              # FastAPI app + middleware + error handlers + router 挂载 + re-export
├── config.py              # 常量 + 环境变量 (~12 lines)
├── schemas.py             # 所有 Pydantic models + 类型别名 + CoreApiError (~250 lines)
├── helpers.py             # 所有工具函数 (~200 lines)
├── agent.py               # Agent 循环 + planner + tool 执行 (~480 lines)
├── store.py               # InMemoryProjectStore + CoreAuthSessionStore + 全局实例 (~560 lines)
├── routers/
│   ├── __init__.py        # 聚合 APIRouter
│   ├── projects.py        # /api/v1/projects/* 全部路由 (~50 lines)
│   ├── auth.py            # /api/v1/auth/session 路由 (~15 lines)
│   └── system.py          # /, /health, /runtime/capabilities, WebSocket events (~60 lines)
├── context_engineering.py # 不变
├── local_state_repository.py # 不变
├── storage_paths.py       # 不变
├── workspace_manager.py   # 不变
└── tests/                 # 测试文件无需修改（server.py re-export 保持兼容）
```

## 各模块内容

### 1. `config.py` — 从 server.py 提取 lines 20-27

```python
import os

APP_VERSION = "0.8.0-edit-draft"
REWRITE_PHASE = "clean_room_rewrite"
CORE_MODE = "local_persistence_bootstrap"
DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001"
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", DEFAULT_SERVER_BASE_URL).rstrip("/")
SERVER_CHAT_MODEL = os.getenv("SERVER_CHAT_MODEL", "entro-reasoning-v1").strip() or "entro-reasoning-v1"
SERVER_CHAT_TIMEOUT_SECONDS = float(os.getenv("SERVER_CHAT_TIMEOUT_SECONDS", "30"))
AGENT_LOOP_MAX_ITERATIONS = int(os.getenv("AGENT_LOOP_MAX_ITERATIONS", "3"))
```

### 2. `schemas.py` — 从 server.py 提取 lines 45-311

包含：
- 所有 `Literal` 类型别名（ProjectWorkflowState, AssetType, TaskType 等）
- `CoreApiError` 异常类
- 所有 Pydantic model（ErrorBody, ErrorEnvelope, ProjectModel, EditDraftModel, ChatRequest, PlannerDecisionModel 等）
- `SUPPORTED_TOOL_NAMES` 常量

依赖：仅 `pydantic` + `typing`（无项目内依赖）

### 3. `helpers.py` — 从 server.py 提取 lines 313-529

包含：
- `_now_iso`, `_request_id`, `_entity_id`, `_trimmed`
- `_extract_text_content`, `_derive_title`
- `_media_file_refs`, `_build_assets`, `_build_clips`
- `_draft_from_payload`, `_bump_draft`, `_build_edit_plan`
- `_draft_summary`, `_chat_history_summary`
- `_extract_first_json_object`

依赖：`schemas.py`（使用 Pydantic model 类型）

### 4. `agent.py` — 从 server.py 提取 lines 531-1007

包含：
- `_emit_agent_progress`
- `_build_planner_messages`
- `_request_server_planner_decision`
- `_validate_planner_decision`, `_should_continue_agent_loop`
- `_parse_tool_input_summary`, `_build_tool_call_or_raise`
- `_execute_tool_call_todo`
- `_apply_tool_observation_to_draft_todo`
- `_run_chat_agent_loop`

依赖：`config.py`, `helpers.py`, `schemas.py`, `context_engineering.py`, `store.py`

### 5. `store.py` — 从 server.py 提取 lines 1010-1614

包含：
- `InMemoryProjectStore` 类（lines 1010-1538）
- `CoreAuthSessionStore` 类（lines 1540-1570）
- `_mark_chat_failed` 函数（lines 1572-1610）
- 全局实例：`store`, `auth_session_store`（lines 1613-1614）

依赖：`schemas.py`, `helpers.py`, `local_state_repository.py`, `workspace_manager.py`
延迟导入：`agent.py`（在 `_run_chat` 方法内部 `from agent import _run_chat_agent_loop`）

### 6. `routers/projects.py` — 从 server.py 提取项目相关路由

路由：
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/assets:import`
- `POST /api/v1/projects/{project_id}/chat`
- `POST /api/v1/projects/{project_id}/export`

依赖：`store.py`, `schemas.py`

### 7. `routers/auth.py` — 从 server.py 提取认证路由

路由：
- `POST /api/v1/auth/session`
- `DELETE /api/v1/auth/session`

依赖：`store.py`, `schemas.py`

### 8. `routers/system.py` — 从 server.py 提取系统/元路由

路由：
- `GET /`
- `GET /health`
- `GET /api/v1/runtime/capabilities`
- `WebSocket /api/v1/projects/{project_id}/events`

依赖：`store.py`, `schemas.py`, `config.py`

### 9. `routers/__init__.py`

```python
from fastapi import APIRouter
from routers.projects import router as projects_router
from routers.auth import router as auth_router
from routers.system import router as system_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(auth_router)
api_router.include_router(system_router)
```

### 10. `server.py`（瘦身后的入口文件）

保留：
- FastAPI app 创建
- CORS middleware
- `request_context_middleware`
- `core_api_error_handler` + `unhandled_error_handler`
- Router 挂载：`app.include_router(api_router)`
- **Re-export**（保持测试兼容）：

```python
from store import store, auth_session_store, InMemoryProjectStore, CoreAuthSessionStore
from config import AGENT_LOOP_MAX_ITERATIONS
```

## 模块依赖关系

```
config.py ← schemas.py ← helpers.py ← agent.py ← store.py ← server.py
                                          ↑              ↓ (lazy import)
                                          └──────────────┘
routers/*.py → store.py, schemas.py, config.py
server.py → routers, store.py, schemas.py, config.py
```

**循环依赖处理**：`store.py` ↔ `agent.py`
- `store.py` 在 `_run_chat()` 方法内使用延迟导入：`from agent import _run_chat_agent_loop`
- `agent.py` 在顶层导入：`from store import store`（store.py 先于 agent.py 加载）

## 加载顺序保证

1. `server.py` 启动 → 导入 `store.py` → store.py 加载完成，创建全局实例
2. `server.py` → 导入 `routers/` → routers 导入 store（已加载）✓
3. 运行时 `store._run_chat()` → 延迟导入 `agent.py` → agent.py 导入 store（已加载）✓

## 测试兼容性

测试文件 `test_server_toolchain_integration.py` 通过 importlib 动态加载 server.py，并引用：
- `core_server.app` → server.py 中的 app ✓
- `core_server.store` → server.py re-export from store.py ✓
- `core_server.auth_session_store` → server.py re-export ✓
- `core_server.InMemoryProjectStore` → server.py re-export ✓
- `core_server.CoreAuthSessionStore` → server.py re-export ✓
- `core_server.AGENT_LOOP_MAX_ITERATIONS` → server.py re-export ✓

测试文件**无需修改**。

## 执行步骤

1. 创建 `core/config.py`，写入配置常量
2. 创建 `core/schemas.py`，写入所有模型和类型定义
3. 创建 `core/helpers.py`，写入所有工具函数
4. 创建 `core/agent.py`，写入 Agent 循环相关函数
5. 创建 `core/store.py`，写入 Store 类和全局实例（使用延迟导入解决循环依赖）
6. 创建 `core/routers/` 目录及 `__init__.py`, `projects.py`, `auth.py`, `system.py`
7. 重写 `core/server.py` 为精简入口文件
8. 运行测试验证：`cd core && python -m pytest tests/ -v`

## 验证方式

1. 启动服务：`cd core && uvicorn server:app --port 8000` 确认无 import 错误
2. 运行集成测试：`cd core && python -m pytest tests/test_server_toolchain_integration.py -v`
3. 检查 `/health` 端点响应正常
