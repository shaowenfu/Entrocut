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

它现在处在一个中间阶段：

1. 本地项目、素材导入、`WorkspaceSnapshot`、导出任务、`WebSocket event stream（事件流）` 已经存在
2. 本地数据层已经进入 `SQLite + project workspace dir + auth session mirror` 形态
3. `chat` 已经进入 `planner-driven` 骨架
4. 真实 `tool execution loop（工具执行循环）` 还没有在 `core` 内彻底落地，仍保留 `TODO` 边界

换句话说，`core` 当前是：

`本地状态中心 + 本地契约服务 + SQLite-backed local backend + 正在收口中的 agent 主链`

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

1. `GET /health`
2. `GET /api/v1/runtime/capabilities`
3. `GET /api/v1/projects`
4. `POST /api/v1/projects`
5. `GET /api/v1/projects/{project_id}`
6. `POST /api/v1/projects/{project_id}/assets:import`
7. `POST /api/v1/projects/{project_id}/chat`
8. `POST /api/v1/projects/{project_id}/export`
9. `POST /api/v1/auth/session`
10. `DELETE /api/v1/auth/session`

### WebSocket

1. `GET /api/v1/projects/{project_id}/events`

当前 `WebSocket` 已用于推送：

1. `task.updated`
2. `workspace.snapshot`
3. `edit_draft.updated`
4. `project.updated`
5. `chat.turn.created`
6. `error.occurred`

## chat 主链的当前状态

`/api/v1/projects/{project_id}/chat` 现在已经不是“用户输入直接触发工具链”的旧逻辑。

当前主链是：

1. 接收用户输入
2. 读取当前 `workspace snapshot`
3. 汇总最近对话摘要
4. 组装 `planner context`
5. 调用 `Server /v1/chat/completions`
6. 解析严格 `JSON planner decision（结构化规划决策）`
7. 进入最小 `agent loop`

当前明确保留的边界：

1. `planner` 已能驱动最小多轮 loop
2. `read / retrieve / inspect / patch / preview` 的 loop 形状已经接入
3. 当前仍保留 `placeholder_first_cut（占位初剪）` 作为原型期的最小可运行路径
4. 工具和草案写回仍是最小原型实现，不是最终生产形态

这意味着：

`core/chat` 的框架方向已经正确，但真实的生产级 planner -> tool -> replanning 闭环仍是下一步重点。`

换句话说，`/chat` 的真正目标不是“回复一句话”，而是：

`让一次对话成为一次围绕 EditDraft 的收敛推进。`

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

当前主要看这几个文件：

1. [server.py](./server.py)
2. [local_state_repository.py](./local_state_repository.py)
3. [workspace_manager.py](./workspace_manager.py)
4. [storage_paths.py](./storage_paths.py)
5. [tests/test_server_toolchain_integration.py](./tests/test_server_toolchain_integration.py)

如果想先理解契约和结构，建议同时看：

1. [docs/contracts/01_core_api_ws_contract.md](../docs/contracts/01_core_api_ws_contract.md)
2. [docs/editing/01_edit_draft_schema.md](../docs/editing/01_edit_draft_schema.md)
3. [docs/agent_runtime/02_editing_agent_runtime_architecture.md](../docs/agent_runtime/02_editing_agent_runtime_architecture.md)

## 本地启动

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

## 当前最应该做的事

如果继续推进 `core`，最应该做的不是再扩接口，而是：

`把 planner -> tool execution -> replanning 的真实生产级 agent loop 落到 core/chat 主链里。`
