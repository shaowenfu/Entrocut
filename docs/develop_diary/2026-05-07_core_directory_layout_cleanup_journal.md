# 2026-05-07 Core 目录整理日志

## 背景

`core/` 在端到端调试前暴露出明显的 flat layout（扁平目录）问题：`FastAPI` 入口、router（路由器）、`Schema`（数据契约）、应用服务层、agent loop（智能体循环）、媒体处理和持久化代码都堆在根目录。虽然功能链路已经闭合，但人工调试时很难快速判断接口定义、事件广播、任务状态和媒体处理分别位于哪里。

本轮目标只做目录整理，不改变 HTTP API、WebSocket 事件、`Pydantic Schema` 字段、任务语义或业务执行逻辑。

## 变更

1. 新增 `core/main.py` 作为标准 `FastAPI` app 入口，启动命令切换为 `uvicorn main:app`。
2. 删除旧根目录 shim（兼容层），测试和调用方统一改用新 package 路径。
3. 将 router 移入 `core/api/routers/`。
4. 将 `schemas.py` 移入 `core/contracts/__init__.py`。
5. 将应用编排移入 `core/application/`。
6. 将 agent 相关执行链移入 `core/agent_runtime/`。
7. 将媒体导入与渲染移入 `core/media/`。
8. 将 SQLite 持久化移入 `core/persistence/`。
9. 将 workspace、storage、helper 移入 `core/runtime/`。
10. 测试中的 patch target（补丁目标）同步改为 `application.store.*`、`media.ingestion.*`、`agent_runtime.agent.*` 等真实模块路径。

## 非目标

- 不拆分 `application/store.py` 内部职责。
- 不替换 WebSocket 为 SSE。
- 不调整 `EditDraft`、`TaskModel`、`EventEnvelope` 等契约。
- 不改变前端事件消费逻辑。
- 不拆分 `contracts/__init__.py` 内部 Schema。

## 验证

- `source venv/bin/activate && python -c "import main; ..."` 可加载新入口。
- `source venv/bin/activate && python -m compileall main.py api application agent_runtime contracts media persistence runtime` 可完成编译检查。

后续若继续降低调试成本，建议优先从 `application/store.py` 中抽出 event bus（事件总线）和 task lifecycle（任务生命周期）边界，而不是立即重写业务流程。
