# EntroCut 审查邮件

各位工程师：

我已接管当前工作区并完成一轮全局审计、回归验证、单元测试补齐和测试资产清理。当前结论不是“代码不可用”，而是“主链路已经能跑，但存在多处骨架与末端实现脱节、测试资产失真、以及部分 UI/服务仍停留在假动作”。

这封邮件的目标只有三个：

1. 明确当前代码库真实状态。
2. 明确我已经立即修掉的问题。
3. 明确接下来每位工程师的收敛任务，避免继续在同一工作区内互相覆盖。

---

## 一、 本轮审计范围

我审计并验证了以下内容：

1. 架构基线文档：
   - `EntroCut_architecture.md`
   - `EntroCut_algorithm.md`
   - `EntroCut_launchpad_design.md`
   - `EntroCut_user_senerio.md`
2. 分工与完成记录：
   - `PHASE45_ENGINEER_TASK_EMAILS_V2.md`
   - `任务完成情况.md`
3. 三端关键实现：
   - `client/src/store/useLaunchpadStore.ts`
   - `client/src/store/useWorkspaceStore.ts`
   - `client/src/services/coreEvents.ts`
   - `core/server.py`
   - `server/main.py`
4. 现有测试与脚本：
   - `scripts/phase45_smoke_test.sh`
   - `scripts/phase45_server_plan_stability.sh`
   - `scripts/phase45_disconnect_recovery_test.sh`
   - `scripts/phase45_prompt_queue_last_only_check.sh`
   - `scripts/smoke_test.sh`

---

## 二、 我确认过的真实链路状态

### 1. 已经打通且验证通过的链路

| 链路 | 当前状态 | 说明 |
| --- | --- | --- |
| Launchpad 创建空项目 -> Workspace 初始化 | 通过 | `Client -> Core` 主入口可用 |
| 浏览器上传视频 -> Core ingest -> Core index proxy -> Server chat -> WS 回流 | 通过 | `phase45_smoke_test.sh` 已通过 |
| Prompt-only -> Core Context Engineering -> Server clarification -> Workspace awaiting_media | 通过 | Prompt-only 状态机现在不是前端假文案 |
| WebSocket 鉴权 / session.ready / event sequence | 通过 | `session_id + last_sequence + request_id` 已在主链路生效 |
| Server down / recovery / Core reconnect | 通过 | `phase45_disconnect_recovery_test.sh` 已通过 |
| Prompt queue 只保留最后一条 | 通过 | 客户端回归脚本通过 |
| Server 规划结果结构稳定性 | 通过 | `reasoning_summary / ops / storyboard_scenes` 稳定 |

### 2. 仍然存在但尚未完全收口的链路

| 链路 | 当前状态 | 真实问题 |
| --- | --- | --- |
| `POST /api/v1/search` | 未完成 | Core 仍返回 `501 NOT_IMPLEMENTED` |
| Launchpad / Workspace 真实 `Render / Export` UI 动作 | 部分完成 | Core 已有最小 render 路由，但 UI 导出按钮仍是假动画 |
| Core ingest 新工作流接入 | 未完成 | `core/app/workflows/ingest.py` 与 `asset_repository.py` 等实现存在，但主入口仍主要走 legacy `_generate_clips_for_assets` |
| Server 向量检索 HTTP 路由 | 未完成 | `VectorSearchService` 已有，但对外缺少稳定 `/search` 合约 |
| Project repository 迁移 | 未完成 | `core/app/repositories/project_repository.py` 仍是 skeleton |

---

## 三、 本轮我已经立即修掉的问题

### 1. 修掉了测试脚本的“假失败”

之前 `phase45_server_plan_stability.sh` 和 `phase45_disconnect_recovery_test.sh` 的失败，不是业务逻辑直接坏掉，而是测试脚本本身有两个问题：

1. `curl` 没有显式绕过本机代理，导致健康检查错误地打到代理端口。
2. 后台 `uvicorn` / `vite` 进程没有彻底脱离 `stdin`，在某些运行环境下会提前退出。

我已统一修正：

1. 所有本机回环 `curl` 增加 `--noproxy '*'`
2. 所有后台进程增加 `NO_PROXY=127.0.0.1,localhost`
3. 所有后台启动命令统一改为 `< /dev/null`

涉及文件：

1. `scripts/phase45_server_plan_stability.sh`
2. `scripts/phase45_disconnect_recovery_test.sh`
3. `scripts/phase45_smoke_test.sh`
4. `scripts/smoke_test.sh`
5. `scripts/dev_up.sh`

### 2. 收口了 Client 侧重复的 WebSocket 管理

当前工作区最明显的冲突点之一，是 `Client` 同时存在两套 `WebSocket` 状态管理：

1. `useWorkspaceStore.ts` 自己维护真实连接
2. `useWorkspaceEventStore.ts` 维护另一套“重连状态”

问题是页面展示用到了第二套状态，但真实消息流来自第一套状态，导致“重连状态 UI”与“真实连接源”脱节。这是典型的并行协作重叠实现。

我已做的修复：

1. 删除废弃的 `client/src/store/useWorkspaceEventStore.ts`
2. 把重连 / resume / `last_sequence` 收口到 `client/src/services/coreEvents.ts`
3. `useWorkspaceStore.ts` 直接接入 managed socket
4. `WorkspacePage.tsx` 只消费一套连接状态

### 3. 把 Server runtime/proxy 接回主流程

工程师 C / D 已经完成了：

1. `LLMProxyService`
2. `EmbeddingProxyService`
3. `VectorSearchService`
4. 阿里云 provider / mock fallback / quota 语义

但在审计时我确认到，`server/main.py` 的主链路基本没有实际使用这些 runtime service。这会造成“代码写了，但生产路径没有吃到”。

我已做的修复：

1. `server/main.py::_run_index_job()` 现在会先走 `_SERVER_RUNTIME.vector_search.upsert_clips(...)`
2. `server/main.py::_run_chat_job()` 现在会走 `_SERVER_RUNTIME.llm_proxy.plan_edit(...)`
3. 保留现有 SQLite `indexed_clips` 作为本地投影，避免破坏当前 contract 组装

### 4. 补上了最小单元测试体系

当前仓库原先几乎没有成体系的 unit test，只有 ad-hoc shell smoke。

我新增了：

1. `core/tests/test_context_engineering.py`
2. `core/tests/test_websocket_hub.py`
3. `core/tests/test_tools.py`
4. `server/tests/test_proxy_services.py`
5. `scripts/test_unit.sh`

覆盖范围：

1. `Core Context Engineering`
2. `WebSocket event sequencing / replay`
3. `Path normalization / media scan / ingest coordinator / preview / export`
4. `Server LLM payload normalization`
5. `Vector search scope / quota`
6. `Embedding quota`
7. `Client prompt queue regression`

### 5. 清掉了废弃测试脚本

我删除了已失效且不符合当前规范的 `scripts/phase45_engineer_b_regression.sh`。

删除原因：

1. 使用 `python3`，违背当前仓库执行规范
2. 是 ad-hoc inline assert，不利于可维护回归
3. 已被 `core/tests/*.py` 与 `scripts/test_unit.sh` 覆盖

同时同步更新了：

1. `core/README_B_TASKS.md`

---

## 四、 当前回归结果

### 已通过

1. `bash scripts/test_unit.sh`
2. `bash scripts/phase45_smoke_test.sh`
3. `bash scripts/phase45_server_plan_stability.sh`
4. `bash scripts/phase45_disconnect_recovery_test.sh`

### 说明

1. `phase45_server_plan_stability.sh`
2. `phase45_disconnect_recovery_test.sh`

这两条在当前工具环境下需要脱离沙盒执行本机回环通信；脚本本身已经修正，在线下/CI 真实环境中可直接执行。

---

## 五、 本轮新发现但尚未收口的关键问题

### P0

1. `core/server.py` 的 `POST /api/v1/search` 仍然是 `501`
2. `WorkspacePage.tsx` 的导出按钮仍是前端假动画，没有真正调用 `Core /api/v1/render`

### P1

1. `core/app/workflows/ingest.py`、`asset_repository.py`、`ingest_state_repository.py` 已存在，但 `core/server.py::_process_ingest_job()` 仍主要走 legacy 逻辑
2. `server/main.py` 仍缺少正式的对外向量检索接口，`VectorSearchService` 现在只被 index job 消费
3. `core/app/repositories/project_repository.py` 仍是 skeleton，未承接真实 SQLite 访问

### P2

1. `server/main.py` 的 `health/runtime_capabilities` 仍然使用静态 adapter 名称，未完全反映 real/mock mode
2. `core/README.md` 还把 `search` 标注为占位，需要后续同步

---

## 六、 接下来每位工程师的收敛任务

### 工程师 A

你的下一轮任务不是继续加视觉细节，而是把 `Workspace` 的“假导出动作”替换为真实 API 触发，并清理剩余前端假状态。

请处理：

1. `WorkspacePage.tsx` 的 `handleExport()` 假动画
2. `client/src/services/coreApi.ts` 增加 `render` 调用
3. `Launchpad / Workspace` 对 `workflow_state` 的 UI 提示统一

禁止做：

1. 不要改 `Core`/`Server` contract
2. 不要重新引入第二套 `WebSocket` store

### 工程师 B

你的代码价值很高，但当前最大问题是“实现存在，主链路未接入”。

请处理：

1. 把 `core/app/workflows/ingest.py` 正式接入 `core/server.py::_process_ingest_job()`
2. 把 `asset_repository.py` / `ingest_state_repository.py` 用到真实 ingest 路径
3. 用新增 unit test 继续覆盖增量 ingest / full ingest 分支
4. 配合工程师 A，把 `render_workflow` 的输出 contract 固化

禁止做：

1. 不要在 `Client` 侧写媒体处理逻辑
2. 不要把云端 provider 直接写进 `Core`

### 工程师 C

你的 provider 代码现在已经部分接入，但检索主链路仍未闭环。

请处理：

1. 增加稳定的 Server 向量检索 HTTP 合约
2. 让 `Core /api/v1/search` 不再返回 `501`
3. 让 `runtime capabilities / health` 动态反映 real/mock provider 状态
4. 为真实 provider 和 mock fallback 补充服务级回归说明

禁止做：

1. 不要改 `Client`
2. 不要把检索逻辑塞回 `Core`

### 工程师 D

你已经把验证矩阵搭起来了，下一轮重点是让它和新增 unit test / render / search 继续对齐。

请处理：

1. 新增 `render` 主链路 smoke
2. 新增 `search` 主链路 smoke
3. 将当前 `scripts/test_unit.sh` 接入完整验证矩阵
4. 清理仍然引用旧测试方式的文档和脚本说明

禁止做：

1. 不要在测试脚本中写新的业务逻辑
2. 不要修改状态机定义

### 我作为主工程师

我下一轮继续负责：

1. 冻结 `search / render / ingest` 的 contract
2. 拆掉 `core/server.py` 中仍然过重的 legacy 逻辑
3. 推进 `ProjectRepository` 和 runtime 装配层迁移
4. 持续清理“实现写在一边、主链路走另一边”的重复结构

---

## 七、 协作纪律

在同一工作区继续协作，必须遵守下面四条：

1. 任何人不要再新增第二套状态源。
2. 任何人不要把 mock 逻辑直接写进主入口路由。
3. 任何人新增脚本时，必须显式处理 `NO_PROXY` 和后台进程 `stdin` 生命周期。
4. 所有回归都统一以 `scripts/test_unit.sh` + `phase45 smoke/disconnect/plan` 为基线。

---

## 八、 当前结论

项目已经从“看起来能跑，但验证不可信、实现与骨架脱节”回到“主链路可信、回归基线存在、下一轮可以继续拆任务”的状态。

但这还不是可以放任并行开发的状态。下一轮必须围绕以下三个收口：

1. `search` 真正闭环
2. `render/export` 从 UI 假动作变成真实调用
3. `Core ingest` 从 legacy 路径迁移到已经存在的新 workflow/repository

在这三个点完成前，不允许再扩展新的产品功能。
