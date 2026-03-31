# Core

`core/` 是本地 `FastAPI（服务框架）` 进程，当前承担三类职责：

1. 本地项目与 `EditDraft（剪辑草案）` 状态管理
2. `Client -> Core` 本地契约落点
3. `planner-driven（规划驱动）` 的 `chat` 主链与本地数据层

## 为什么是 Core

从第一性原理看，视频剪辑的本质不是“操作时间线”，而是：

`从候选片段集合里，围绕用户 intent（意图）不断做 select -> compose -> evaluate -> revise，直到形成可执行的 EditDraft。`

这也意味着 `core` 的真实职责不是“暴露几个本地接口”，而是：

1. 保存当前剪辑事实
2. 给 `planner` 提供决策所需的最小上下文
3. 驱动 `retrieve / inspect / patch / preview` 这些高层能力
4. 把每一步结果回写成新的 `EditDraft`

所以 `core` 本质上是：

`本地剪辑状态中心 + agent 执行闭环承载层`

## 当前定位

当前 `core` 不是“只剩 health 的壳层”，也不是最终完整 `agent engine（智能体引擎）`。

它现在处在一个清晰但仍在继续收口的阶段：

1. 本地项目、素材导入、`WorkspaceSnapshot`、导出任务、`WebSocket event stream（事件流）` 已经存在
2. 本地数据层已经进入 `SQLite + project workspace dir + auth session mirror` 形态
3. `chat` 已经进入 `planner-driven` 最小闭环
4. `tool execution` 与草案写回已经能跑通最小原型，但还不是最终生产实现

换句话说，`core` 当前是：

`本地状态中心 + 本地契约服务 + SQLite-backed local backend + 已拆分成模块的 agent 主链入口`

## 当前模块结构

`core/server.py` 已经不再承载所有逻辑，而是缩成装配层。当前主要模块是：

1. [server.py](./server.py)
   - `FastAPI app` 创建
   - `CORS middleware`
   - `request_context_middleware`
   - 异常处理
   - router 挂载
   - 兼容性 `re-export`
2. [config.py](./config.py)
   - 环境变量与运行时常量
3. [schemas.py](./schemas.py)
   - `Pydantic models（数据模型）`
   - `Literal` 类型别名
   - `CoreApiError`
4. [helpers.py](./helpers.py)
   - 纯工具函数
   - 草案派生与摘要构建
5. [agent.py](./agent.py)
   - `planner request`
   - 最小 `agent loop`
   - `tool observation` 写回
6. [store.py](./store.py)
   - `InMemoryProjectStore`
   - `CoreAuthSessionStore`
   - 后台任务与事件广播
7. [routers/](./routers/)
   - `projects.py`
   - `auth.py`
   - `system.py`
8. [state.py](./state.py)
   - 本地 `SQLite repository`
9. [workspace_manager.py](./workspace_manager.py)
   - 项目工作目录与导出落点管理
10. [storage_paths.py](./storage_paths.py)
    - 本地存储路径解析
11. [context.py](./context.py)
    - `planner context packet` 组装

当前依赖方向大致是：

`config -> schemas -> helpers -> agent -> store -> routers/server`

其中 `store -> agent` 通过运行时 `lazy import（延迟导入）` 处理，避免循环依赖。

## 当前本地数据层

当前 `core` 的本地数据层已经不是纯内存态，而是：

1. `SQLite`
   - 保存 `projects / edit_drafts / chat_turns / tasks / project_runtime / assets / core_auth_session`
2. `project workspace dir`
   - 在 `create_project` 时自动初始化
   - 目录固定为 `thumbs / preview / exports / temp / proxies`
3. `auth session mirror`
   - `core` 本地只保存 `access_token / user_id` 镜像
   - 不保存 `refresh_token`

当前原则：

1. 原始素材只保存路径引用
2. 导出产物写入项目工作目录
3. `client` 不直接感知数据库

## 当前真实能力

### HTTP

1. `GET /`
2. `GET /health`
3. `GET /api/v1/runtime/capabilities`
4. `GET /api/v1/projects`
5. `POST /api/v1/projects`
6. `GET /api/v1/projects/{project_id}`
7. `POST /api/v1/projects/{project_id}/assets:import`
8. `POST /api/v1/projects/{project_id}/chat`
9. `POST /api/v1/projects/{project_id}/export`
10. `POST /api/v1/auth/session`
11. `DELETE /api/v1/auth/session`

### WebSocket

1. `GET /api/v1/projects/{project_id}/events`

当前 `WebSocket` 已用于推送：

1. `task.updated`
2. `workspace.snapshot`
3. `edit_draft.updated`
4. `project.updated`
5. `chat.turn.created`
6. `error.occurred`
7. `agent.step.updated`

## chat 主链的当前状态

`/api/v1/projects/{project_id}/chat` 现在的真实主链是：

1. 接收用户输入
2. 读取当前 `workspace snapshot`
3. 汇总最近对话摘要
4. 组装 `planner context`
5. 调用 `Server /v1/chat/completions`
6. 解析严格 `JSON planner decision（结构化规划决策）`
7. 进入最小 `agent loop`
8. 在需要时执行 `read / retrieve / inspect / patch / preview`
9. 将结果回写为新的 `EditDraft`

当前仍然明确保留的原型边界：

1. `placeholder_first_cut（占位初剪）` 仍是最小可运行路径之一
2. `tool execution` 还不是最终生产级实现
3. 真正复杂的精剪、排序、质量判断仍需要继续演进

这意味着：

`/chat` 的目标不是“回复一句话”，而是让一次对话成为一次围绕 EditDraft 的收敛推进。`

## 当前事实源

`core` 当前围绕 `EditDraft` 工作，而不是围绕展示型 `Storyboard` 工作。

系统里的基本层次是：

1. `Asset`
2. `Clip`
3. `Shot`
4. `Scene`
5. `EditDraft`

其中：

1. `clip` 是分析/检索单元
2. `shot` 是最小可编辑语义单元
3. `scene` 是可选工作分组层
4. 最终执行语义以 `EditDraft.shots` 为准

## 当前非目标

当前 `core` 明确还不做这些事：

1. 不在本地直接持有云端 `LLM / Embedding / DashVector` 密钥
2. 不在 `chat` 主链里绕过 `planner` 直接偷跑工具
3. 不实现完整时间线编辑器
4. 不实现复杂精剪、关键帧动画、特效编排
5. 不把 `scene` 固化成强叙事模板

## 代码入口

如果想快速理解当前实现，建议按这个顺序看：

1. [server.py](./server.py)
2. [routers/projects.py](./routers/projects.py)
3. [store.py](./store.py)
4. [agent.py](./agent.py)
5. [schemas.py](./schemas.py)
6. [state.py](./state.py)
7. [context.py](./context.py)
8. [manager.py](./manager.py)
9. [tests/test_server_toolchain_integration.py](./tests/test_server_toolchain_integration.py)

如果想先理解契约和设计背景，建议同时看：

1. [docs/data&contract/01_core_api_ws_contract.md](../docs/data&contract/01_core_api_ws_contract.md)
2. [docs/editing/01_edit_draft_schema.md](../docs/editing/01_edit_draft_schema.md)
3. [docs/agent_runtime/02_editing_agent_runtime_architecture.md](../docs/agent_runtime/02_editing_agent_runtime_architecture.md)
4. [docs/develop_diary/2026-03-30_core_module_reconstruct_journal.md](../docs/develop_diary/2026-03-30_core_module_reconstruct_journal.md)

## 本地启动

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

## 测试

当前仓库里的 `core` 测试可以直接跑：

```bash
cd core
source venv/bin/activate
python -m unittest discover tests -v
```

## 当前最应该做的事

如果继续推进 `core`，最值得投入的不是再扩接口，而是：

`把 planner -> tool execution -> replanning 的真实生产级 agent loop 继续收口到 core/chat 主链里。`
