# EntroCut

`EntroCut` 是一个早期阶段的 `Chat-to-Cut（对话到剪辑）` 开源探索项目。它尝试把视频剪辑从“手动操作时间线”推进到“用自然语言持续收敛剪辑草案”：

```text
intent（意图）
  -> retrieve（找素材）
  -> inspect（判断候选）
  -> patch（修改草案）
  -> preview/export（预览与导出）
```

项目当前还不是成熟产品，也不是通用剪辑软件的替代品。更准确地说，它是一个正在成型的 `editing agent（剪辑智能体）` 原型系统：已经跑通了桌面端、本地 `core`、云端 `server` 的基本闭环，但 `planner（规划器）` 质量、长链路稳定性、素材理解效果和产品体验还在持续打磨。

## 项目愿景

视频剪辑的核心不是拖动时间线本身，而是从原始素材里选择、排序、裁切、组织出一个能表达意图的观看序列。

`EntroCut` 的长期愿景是：

> 让用户通过自然语言把模糊剪辑目标逐步收敛成可执行、可预览、可修改的 `EditDraft（剪辑草案）`。

这意味着项目关注的不是“一句话直接生成最终大片”，而是 `iterative convergence（迭代收敛）`：

1. 用户表达目标。
2. 系统建立结构化 `EditDraft`。
3. `agent loop（智能体循环）` 根据上下文调用工具。
4. 用户通过预览、反馈、局部选择继续修正。
5. 最终导出一个可播放的视频结果。

## 当前开发现状

当前仓库已经形成三端结构：

- `client/`：桌面前端，基于 `Electron + React + Vite + Zustand`。
- `core/`：本地后端，基于 `FastAPI + SQLite + ffmpeg`，维护本地项目、素材导入、`EditDraft`、预览与导出。
- `server/`：云端能力网关，基于 `FastAPI`，提供认证、`chat proxy（聊天代理）`、向量化、检索和视觉精判能力。

已经比较明确的部分：

1. `Launchpad -> Workspace -> import -> chat -> preview/export` 的最小闭环已经成立。
2. `EditDraft` 已经成为核心事实源，`storyboard（故事板）` 只是 UI 派生视图。
3. `core` 已经从纯原型状态推进到 `SQLite-backed local backend（基于 SQLite 的本地后端）`。
4. `server` 已经具备 `Google/GitHub OAuth`、`JWT（JSON Web Token）`、`OpenAI-compatible chat proxy`、`vectorize/retrieval/inspect` 等主链能力。
5. 桌面端已能托管本地 `core` 进程，并通过 `Electron IPC（进程间通信）` 接入本地媒体能力。

仍在收口的部分：

1. `planner` 的决策质量和多轮稳定性仍需继续优化。
2. `retrieve / inspect / patch / preview` 的工具链已经接入，但端到端效果还需要更多真实素材验证。
3. `preview/export` 已有真实渲染产物，但编码参数、性能、音频与失败恢复还不是最终生产形态。
4. `credits / BYOK（用户自带密钥） / provider compatibility（供应商兼容性）` 仍需要更系统的回归。
5. 项目文档正在从开发笔记整理为更稳定的开源入口。

## 三端 README 导航

更细的工程现状请直接看子目录 README：

| 模块 | 说明 | 文档 |
| --- | --- | --- |
| `client/` | 桌面前端、项目入口、工作台、Electron 本地能力桥接 | [client/README.md](./client/README.md) |
| `core/` | 本地项目事实源、素材导入、agent loop、preview/export | [core/README.md](./core/README.md) |
| `server/` | 云端认证、模型网关、向量检索、视觉 inspect | [server/README.md](./server/README.md) |

## 当前项目结构

根目录只保留高层导航；各端内部文件结构请看对应 README。

```text
Entrocut/
├── client/                       # Electron + React 桌面前端
├── core/                         # 本地 FastAPI 后端与剪辑事实源
├── server/                       # 云端 FastAPI 能力网关
├── docs/                         # 设计文档、开发记录、任务说明
├── scripts/                      # 仓库级启动、冒烟、staging 辅助脚本
├── logs/                         # 本地运行日志
├── temp/                         # 临时文件与短生命周期产物
├── docker-compose.production.yml # server 生产部署相关编排入口
└── README.md                     # 项目总入口
```

常见生成物不属于核心源码：`client/dist/`、`client/dist-electron/`、`client/release/`、`client/node_modules/`、`core/dist/`、`core/build/`、`core/venv/`、`server/venv/`。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Desktop UI（桌面界面） | `Electron`、`React`、`Vite`、`TypeScript`、`Zustand` |
| Local Core（本地核心） | `Python`、`FastAPI`、`SQLite`、`WebSocket`、`ffmpeg`、`SceneDetect` |
| Cloud Server（云端服务） | `Python`、`FastAPI`、`MongoDB`、`Redis`、`DashScope`、`DashVector`、`Gemini/OpenAI-compatible API` |
| Packaging（打包） | `electron-builder`、`PyInstaller` |

## 本地启动

最简单方式：

```bash
./scripts/dev_up.sh
```

手动启动时建议分别开三个终端。

### client

```bash
cd client
npm install
npm run dev -- --host 127.0.0.1 --port 5173
npm run electron:dev
```

### core

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

### server

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## 推荐阅读路径

如果你是第一次进入项目，建议按这个顺序读：

1. [client/README.md](./client/README.md)：先理解桌面入口和用户工作流。
2. [core/README.md](./core/README.md)：再理解本地事实源、素材导入、`EditDraft` 和渲染闭环。
3. [server/README.md](./server/README.md)：最后理解云端认证、模型代理、检索和 inspect。
4. [docs/README.md](./docs/README.md)：需要深入设计脉络时，再进入完整文档索引。
5. [docs/editing/01_edit_draft_schema.md](./docs/editing/01_edit_draft_schema.md)：理解 `EditDraft` 的核心数据模型。
6. [docs/agent_runtime/README.md](./docs/agent_runtime/README.md)：理解 `agent runtime` 的规划、工具、上下文和执行循环。

## 当前 Non-goals

为了控制早期项目复杂度，当前明确不做：

1. 不做完整传统 `timeline editor（时间线编辑器）`。
2. 不追求一次性替代专业剪辑师。
3. 不把 `storyboard` 作为事实源；事实源仍是 `EditDraft`。
4. 不在本地 `core` 里保存云端 refresh token 或第三方密钥。
5. 不承诺当前 `mock` 或 `placeholder_first_cut` 代表最终剪辑质量。
6. 不承诺当前打包、计费、BYOK、provider 兼容性已经达到生产级。

## 开源状态

这是一个早期项目，适合关注系统设计、`agent workflow（智能体工作流）`、视频理解、桌面端本地后端、`LLM tool use（大模型工具调用）` 的开发者阅读和实验。

当前更适合的参与方式：

1. 阅读三端 README，确认系统边界。
2. 用真实短视频素材跑通本地闭环。
3. 针对 `planner`、`retrieval`、`inspect`、`preview/export` 提出可复现问题。
4. 优先补测试、错误语义和文档，而不是提前堆叠新功能。

仓库目前尚未声明稳定版本号和正式 `LICENSE（开源许可证）`。在用于生产、商用或二次分发前，请先确认许可证与依赖授权。
