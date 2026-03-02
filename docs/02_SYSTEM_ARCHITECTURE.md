# 02. System Architecture（系统架构）

## 1. 架构类型

采用 `Hybrid Local-First Architecture（本地优先混合架构）`：

1. 算法与渲染重负载放在本地 `core`。
2. 语义理解与编排放在云端 `server`。
3. 用户交互与进程管理放在桌面端 `client`。

## 2. 分层与职责

### `client/` - The Interface（交互层）

1. 承载 `UI/UX（界面与交互）`。
2. 启动并守护本地 `core Sidecar（侧车进程）`。
3. 管理会话状态、项目状态与可视化反馈。
4. 作为 `core` 与 `server` 的编排入口。

### `core/` - The Engine（本地引擎）

1. 执行素材切分、关键帧抽样、拼图。
2. 执行本地 `FFmpeg` 预览渲染与导出。
3. 维护本地 `AtomicClip（原子片段）` 索引。
4. 暴露本地 HTTP API 给 `client`。

### `server/` - The Brain（云端大脑）

1. 执行 `Prompt Orchestration（提示词编排）`。
2. 调用 `Qwen3-VL-Embedding` 进行向量化。
3. 调用 `DashVector` 执行语义检索（强制 `user_id` 过滤）。
4. 生成 `EntroVideoProject` 契约与 `reasoning`。
5. 管理多轮 `Session（会话）`。

## 3. 拓扑与通信

```text
User
  |
client (Electron + React)
  |--HTTP--> core (localhost, Python FastAPI)
  |--HTTPS-> server (Cloud FastAPI)
               |--> Qwen3-VL-Embedding
               |--> Qwen3-VL-Flash
               |--> DashVector
```

## 4. 依赖方向

1. `client -> core`
2. `client -> server`
3. `core` 不依赖 `client`。
4. `server` 不依赖 `client/core` 实现细节，仅依赖契约输入。
5. 禁止 `core <-> server` 形成隐式循环调用链。

## 5. 性能与边界约束

1. 原始视频不出本地磁盘。
2. 云端仅接收关键帧拼图（Base64）与最小元数据。
3. `Ingest -> First Preview` 目标时延：`<= 60s`（1 小时素材基准）。
4. 大文件数量不设上限，但 `MVP` 不承诺无限性能线性扩展。
