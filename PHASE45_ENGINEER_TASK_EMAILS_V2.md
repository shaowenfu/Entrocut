# Phase 4/5 五名工程师任务邮件

## 邮件 1：主工程师

工程师你好，请你查看 [PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [PHASE45_GIT_COLLAB_PROTOCOL.md](/home/sherwen/MyProjects/Entrocut/PHASE45_GIT_COLLAB_PROTOCOL.md)，你的任务是 [1.1 WebSocket 鉴权与会话建立协议](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[1.6 Prompt-only 项目状态机](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[1.9 Event sequence 与幂等去重机制](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[1.10 Core Context Engineering shell](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [1.11 同项目多任务并发门控](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)。

你的执行边界是：

1. 允许修改：
   1. `core/server.py`
   2. `server/main.py`
   3. `client/src/store/useLaunchpadStore.ts`
   4. `client/src/store/useWorkspaceStore.ts`
   5. `core/app/services/*`
   6. `core/app/workflows/*`
   7. 根目录任务与协作文档
2. 禁止修改：
   1. 真实媒体处理工具实现细节
   2. 真实 `Embedding/DashVector/LLM adapter`
   3. UI 视觉样式细节

请不要影响其它工程师的任务，尤其不要把真实算法实现拉进主入口文件。你的目标是把全局骨架、状态机、鉴权、事件顺序和协作边界全部冻结，为其他四位工程师提供稳定依赖。提交前请给出最小验证命令、残留风险和对主链路影响说明。

## 邮件 2：工程师 A

工程师你好，请你查看 [PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [PHASE45_GIT_COLLAB_PROTOCOL.md](/home/sherwen/MyProjects/Entrocut/PHASE45_GIT_COLLAB_PROTOCOL.md)，你的任务是 [2.2 Electron 路径导入与浏览器上传语义拆分](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[2.3 无素材工作台的显式 UI 限制与引导](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [2.6 WebSocket reconnect 与 resync](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)。

你的执行边界是：

1. 允许修改：
   1. `client/src/pages/*`
   2. `client/src/services/coreEvents.ts`
   3. `client/src/services/electronBridge.ts`
   4. `client/src/services/health.ts`
   5. `client/src/store/` 下除 `useLaunchpadStore.ts`、`useWorkspaceStore.ts` 之外你需要先和主工程师确认的辅助文件
2. 禁止修改：
   1. `core/`
   2. `server/`
   3. `WebSocket event schema`
   4. 根目录设计文档

请不要影响其它工程师的任务。你负责的是 `Client` 侧事件驱动链路的稳定性和入口语义拆分，不要顺手修改 `Core` 和 `Server`。重点是让启动台、工作台在真实断线和无素材场景下行为一致，且不会因为重连产生重复 UI 状态。提交前请附带一条成功路径和一条断线路径的验证说明。

## 邮件 3：工程师 B

工程师你好，请你查看 [PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [PHASE45_GIT_COLLAB_PROTOCOL.md](/home/sherwen/MyProjects/Entrocut/PHASE45_GIT_COLLAB_PROTOCOL.md)，你的任务是 [3.1 Core 资产去重、路径规范化与重扫幂等](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[3.2 Ingest 阶段化进度模型](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[3.3 增量 ingest 与全量重跑的策略切分](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [3.5 Render Preview 与 Export Output 分离](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)。

你的执行边界是：

1. 允许修改：
   1. `core/app/tools/*`
   2. `core/app/repositories/*`
   3. `core/app/workflows/*`
   4. `core/requirements.txt`
   5. `core/README.md`
2. 禁止修改：
   1. `client/`
   2. `server/`
   3. `core/server.py` 的主入口路由和事件名

请不要影响其它工程师的任务。你负责的是 `Core` 本地媒体与资产管理链路，不要把任何云端调用塞进你的工具实现里。所有真实实现都必须挂在现有 `tool/workflow/repository` 骨架后面，不允许绕过骨架直接改主入口。提交前请给出去重、增量 ingest 和 render 边界的最小回归命令。

## 邮件 4：工程师 C

工程师你好，请你查看 [PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [PHASE45_GIT_COLLAB_PROTOCOL.md](/home/sherwen/MyProjects/Entrocut/PHASE45_GIT_COLLAB_PROTOCOL.md)，你的任务是 [4.2 Embedding adapter 真接入](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[4.3 DashVector index/search 真接入](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[4.4 user_id 过滤与检索隔离](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [4.5 Quota / rate limit / provider failure 语义](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)。

你的执行边界是：

1. 允许修改：
   1. `server/app/adapters/*`
   2. `server/app/services/*`
   3. `server/app/repositories/*`
   4. `server/requirements.txt`
   5. `server/README.md`
2. 禁止修改：
   1. `client/`
   2. `core/`
   3. `server/main.py` 的对外路径和响应字段名

请不要影响其它工程师的任务。你负责的是真实云端向量化和检索能力，不要改 UI，也不要把 provider 私货写进 `Core`。必须保留 `mock adapter fallback`，保证其他工程师在你未接好真实服务前仍然能继续开发。提交前请提供一条真实 provider 成功路径和一条限流或失败路径的验证说明。

## 邮件 5：工程师 D

工程师你好，请你查看 [PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [PHASE45_GIT_COLLAB_PROTOCOL.md](/home/sherwen/MyProjects/Entrocut/PHASE45_GIT_COLLAB_PROTOCOL.md)，你的任务是 [4.1 Server 规划结果的结构稳定性](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[5.1 Prompt queue 只保留最后一条的验证矩阵](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)、[5.3 断线恢复测试矩阵](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md) 和 [5.4 一次性三端 smoke 扩展为 CI smoke](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)。

你的执行边界是：

1. 允许修改：
   1. `server/app/adapters/*`
   2. `server/app/services/*`
   3. `scripts/*`
   4. 测试文档
   5. 必要的 CI 辅助脚本
2. 禁止修改：
   1. `client/` 业务代码
   2. `core/` 业务代码
   3. 跨端冻结契约和事件名

请不要影响其它工程师的任务。你负责的是规划结果稳定性和验证体系，不要把新的业务逻辑混进测试脚本里，也不要修改主工程师保留的状态机。你的任务目标是让“正确的规划输出”和“正确的失败行为”都能被重复验证，而不是追求功能更多。提交前请给出至少一条 `smoke` 命令、一条断线恢复测试说明和一条 `Prompt queue` 验证说明。

