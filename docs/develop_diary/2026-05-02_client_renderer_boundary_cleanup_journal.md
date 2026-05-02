# 2026-05-02 Client Renderer 边界收口记录

本轮目标是人工精读 `client` 前，先把容易误导理解的历史包袱清掉，并把 `Electron Main Process（主进程）`、`Renderer Process（渲染进程）`、`core` 的职责边界写清楚。

## 关键判断

1. `client/main` 是桌面宿主层，不负责 UI，也不负责核心业务；它负责窗口、IPC、文件选择、本地媒体协议、secure store、deep link、core 托管。
2. `client/src` 是 Renderer 交互应用层，不只是页面渲染；它承担 UI、前端状态机、core API 适配、事件可视化。
3. Agent 编排事实源应只在 `core`。`core/agent.py` 已经负责 planner context、planner 调用、tool gating、tool execution loop、runtime_state 回写与 `agent.step.updated` 广播。
4. `client/src/agent` 是旧的前端 agent runtime prototype（原型），继续保留会让人误以为 Renderer 可以绕过 core 自行编排 agent。
5. `client/src/mocks` 已无生产引用，且与当前 core-backed client 状态不一致，保留只会干扰阅读。

## 处理结果

1. 给 `client/main/main.ts`、`coreSupervisor.ts`、`preload.ts`、`fileScanner.ts`、`localMediaProtocol.ts` 补充最小必要中文注释，覆盖每个函数和核心变量。
2. 删除 `client/src/agent/`：
   - 移除前端 planner/tool loop。
   - 删除 `WorkspacePage` 的 `Run Agent` 按钮。
   - `useWorkspaceStore` 不再维护前端 `SessionRuntimeState`，只保留轻量 `selectionContext`，用于 chat target。
3. 删除 `client/src/mocks/`：
   - 移除旧 `Launchpad` mock project。
   - 移除旧 `prototypeWorkspace` 内存项目模型。
4. 收敛 Electron 媒体选择入口：
   - 删除 `showOpenDirectory / showOpenVideos`。
   - 删除 `dialog:open-directory / dialog:open-videos`。
   - 保留统一 `showOpenMedia -> dialog:open-media`。
   - 用户选择视频文件时直接返回路径；选择目录时递归扫描支持的视频文件。
5. 更新 `client/README.md`，移除前端 agent prototype 与 mocks 目录说明，明确 agent 编排只在 `core`。

## 当前边界

```text
client/main
  Desktop Adapter / Host Layer
  负责系统能力、安全 IPC、本地媒体协议、core 生命周期

client/src
  Renderer Interaction Layer
  负责 UI、Zustand 状态机、core API 调用、WebSocket 事件展示

core
  Business Engine / Agent Authority
  负责项目事实源、EditDraft、planner/tool loop、任务、事件、持久化
```

## 验证

每个阶段均执行：

```bash
cd client
npm run typecheck
```

删除 `client/src/agent` 与 `client/src/mocks` 后，`typecheck` 通过，说明没有剩余生产引用。

## 后续注意

1. 如果要新增 Agent 能力，应优先进入 `core/agent.py`、`core/context.py`、`core/schemas.py`，而不是恢复前端 agent runtime。
2. `client` 可以展示 `agent.step.updated`，但不应自行决定 planner 下一步或执行 tool。
3. `selectionContext` 是 UI 交互状态，不是 Agent runtime state；它只用于构造 chat target。
4. 如需保留演示数据，应放到明确的测试/fixture 目录，并避免被生产 README 描述为运行时能力。
