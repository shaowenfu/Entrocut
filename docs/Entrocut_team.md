本手册定义了项目启动前的团队分工、环境标准及协同协议，旨在消除开发过程中的集成障碍。协作执行以 `docs/coordination/` 为 SSOT（单一事实源）。

## 1. Team Assignment（团队角色与任务分配）

| 角色 | 核心职责 | 交付物 |
| --- | --- | --- |
| **client-agent（客户端 Agent（代理））** | Electron（桌面框架）架构、React（前端框架）UI（界面）、SQLite（本地数据库）维护 | Electron（桌面应用）壳程序、本地数据库 Schema（结构规范）、UI（界面） |
| **core-agent（算法 Agent（代理））** | Python（解释语言）视频切分、抽帧逻辑、云端 API（接口）调用封装 | Python Sidecar（本地算法服务）执行文件、本地算法服务接口 |
| **server-agent（云端 Agent（代理））** | FastAPI（Python Web 框架）业务逻辑、MongoDB Atlas（云数据库）交互、DashVector（向量数据库）管理 | 业务 API（接口）文档、云端数据库模型、鉴权系统 |
| **data-agent（数据 Agent（代理））** | UI/UX（交互设计）规范、Qwen-VL（多模态模型）提示词优化、JSON Schema（JSON 结构规范）定义 | 交互原型图、System Prompt（系统提示词）字典、Schema（结构规范） |

## 2. Environment Setup（开发环境标准化）

### 本地开发环境要求

- **运行时**: Node.js 20.x+, Python 3.10+（使用 venv（虚拟环境）隔离）
- **工具链**: Git（版本控制）, VS Code（代码编辑器）（推荐插件: Python, ES7+ React（前端框架）, Prisma（ORM））, Postman（接口测试工具）
- **多媒体**: 全局安装 FFmpeg（多媒体工具） 6.0+（开发阶段使用，生产环境将内置）

### 云端资源准备

- **MongoDB Atlas**: 创建专用 Cluster（集群），获取连接字符串并配置 IP 白名单。
- **阿里云百炼**: 获取 `DASHSCOPE_API_KEY`。
- **DashVector**: 创建 1024 维度的向量集合（Collection）。

## 3. Monorepo Structure（目录结构与代码组织）

```
/root
  ├── /client (Electron（桌面框架） + React（前端框架）)
  │     ├── /src (渲染进程: UI（界面）)
  │     ├── /main (主进程: 调度 Node.js（运行时）/SQLite（本地数据库）)
  │     └── /app (Electron 入口)
  ├── /core (Python Sidecar（本地算法服务）)
  │     ├── /detect (镜头切分逻辑)
  │     ├── /process (抽帧与特征上传)
  │     └── server.py (本地 HTTP（协议）接口)
  ├── /server (Cloud Backend（云端后端）)
  │     ├── /models (MongoDB（文档数据库）/DashVector（向量数据库）模型)
  │     ├── /routes (FastAPI（Python Web 框架）路由)
  │     └── main.py
  └── /docs (API（接口）文档与 JSON Schema（JSON 结构规范）)

```

## 4. Collaboration Protocol（协同协议）

协作与轮次节奏以各自的 Agent Doc（代理文档）为准，入口为 `docs/*_agent.md`。

### A. 客户端与本地算法端协同（IPC（进程间通信） + HTTP（协议））

- **通讯模式**：Electron（桌面框架）通过 Sidecar（本地算法服务）模式启动 Python 进程。
- **通讯协议**：Node.js（运行时）通过 `localhost:port` 发送 JSON-RPC（JSON 远程过程调用）请求给 Python。
- **本地存储**：Electron 直接读写 SQLite（本地数据库），Python 仅负责计算并返回结果，不直接修改数据库。

### B. 前后端协同（OpenAPI（接口规范））

- **文档标准**：云端 FastAPI（Python Web 框架）必须强制开启 `/docs`（Swagger（接口文档）），作为前端调用的唯一依据。
- **数据隔离**：所有云端请求头必须携带 `X-User-ID`，后端据此在 MongoDB（文档数据库）和 DashVector（向量数据库）中进行过滤。

### C. 结构化输出协议（JSON Schema（JSON 结构规范））

- 所有 Qwen3-VL-Flash（多模态模型）的输出必须符合 `/docs/schemas/analysis.json` 中定义的字段。core-agent（算法 Agent（代理））与 server-agent（云端 Agent（代理））需共同维护此文件。

## 5. Debugging Strategy（调试方案）

1. **UI（界面）调试**：开启 Electron（桌面框架）开发者工具 DevTools（开发者工具）监控 React（前端框架）状态与网络请求。
2. **算法调试**：Python 侧开启 logging（日志）记录，输出至本地 `debug.log`，Electron 可视化展示日志。
3. **云端调试**：通过 MongoDB Atlas（云数据库）控制台监控实时写入量，利用 DashVector（向量数据库）网页工具验证向量分布。
4. **端到端测试链路**：
    - 上传视频路径 -> Python 切分 -> Python 抽帧上传图片 -> 云端生成向量 -> 返回结果 -> 客户端 SQLite（本地数据库）更新。

## 6. 配置文件管理说明

项目根目录下创建 `.env.example` 文件，统一管理以下变量：

- `ALIBABA_CLOUD_API_KEY`
- `MONGODB_ATLAS_URI`
- `DASHVECTOR_ENDPOINT`
- `LOCAL_PYTHON_PORT` (本地算法通讯端口)
