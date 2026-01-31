本手册定义了项目启动前的团队分工、环境标准及协同协议，旨在消除开发过程中的集成障碍。

## 1. 团队角色与任务分配 (Team Assignment)

| 角色 | 核心职责 | 交付物 |
| --- | --- | --- |
| **客户端开发 (A)** | Electron 架构、React UI、SQLite 维护 | Electron 壳程序、本地数据库 Schema、UI 界面 |
| **算法开发 (B)** | Python 视频切分、抽帧逻辑、云端 API 调用封装 | Python Sidecar 执行文件、本地算法服务接口 |
| **云端开发 (C)** | FastAPI 业务逻辑、MongoDB Atlas 交互、DashVector 管理 | 业务 API 文档、云端数据库模型、鉴权系统 |
| **产品/提示词工程师 (D)** | UI/UX 设计、Qwen-VL 提示词优化、JSON Schema 定义 | 交互原型图、系统提示词 (System Prompt) 字典 |

## 2. 开发环境标准化 (Environment Setup)

### 本地开发环境要求

- **运行时**: Node.js 20.x+, Python 3.10+ (使用 venv 隔离)
- **工具链**: Git (版本控制), VS Code (推荐插件: Python, ES7+ React, Prisma), Postman (接口测试)
- **多媒体**: 全局安装 FFmpeg 6.0+ (开发阶段使用，生产环境将内置)

### 云端资源准备

- **MongoDB Atlas**: 创建专用 Cluster，获取连接字符串并配置 IP 白名单。
- **阿里云百炼**: 获取 `DASHSCOPE_API_KEY`。
- **DashVector**: 创建 1024 维度的向量集合 (Collection)。

## 3. 目录结构与代码组织 (Monorepo Structure)

```
/root
  ├── /client (Electron + React)
  │     ├── /src (渲染进程: UI界面)
  │     ├── /main (主进程: 调度 Node/SQLite)
  │     └── /app (Electron 入口)
  ├── /core (Python Algorithm Sidecar)
  │     ├── /detect (镜头切分逻辑)
  │     ├── /process (抽帧与特征上传)
  │     └── server.py (本地 HTTP 接口)
  ├── /server (Cloud Backend)
  │     ├── /models (MongoDB/DashVector模型)
  │     ├── /routes (FastAPI 路由)
  │     └── main.py
  └── /docs (API 文档与 JSON Schema)

```

## 4. 协同与调试协议 (Collaboration Protocol)

### A. 客户端与本地算法端的协同 (IPC + HTTP)

- **通讯模式**：Electron 通过 `Sidecar` 模式启动 Python 进程。
- **通讯协议**：Node.js 通过 `localhost:port` 发送 JSON-RPC 请求给 Python。
- **本地存储**：Electron 直接读写 SQLite，Python 仅负责计算并返回结果，不直接修改数据库。

### B. 前后端协同 (OpenAPI)

- **文档标准**：云端 FastAPI 必须强制开启 `/docs` (Swagger)，作为前端调用的唯一依据。
- **数据隔离**：所有云端请求头必须携带 `X-User-ID`，后端据此在 MongoDB 和 DashVector 中进行过滤。

### C. 结构化输出协议 (JSON Schema)

- 所有 Qwen3-VL-Flash 的输出必须符合 `/docs/schemas/analysis.json` 中定义的字段。算法开发 (B) 与 云端开发 (C) 需共同维护此文件。

## 5. 调试方案 (Debugging Strategy)

1. **UI 调试**：开启 Electron 开发者工具 (DevTools) 监控 React 状态与网路请求。
2. **算法调试**：Python 侧开启 `logging` 记录，输出至本地 `debug.log`，Electron 可视化展示日志。
3. **云端调试**：通过 MongoDB Atlas 控制台监控实时写入量，利用 DashVector 网页工具验证向量分布。
4. **端到端测试链路**：
    - 上传视频路径 -> Python 切分 -> Python 抽帧上传图片 -> 云端生成向量 -> 返回结果 -> 客户端 SQLite 更新。

## 6. 配置文件管理说明

项目根目录下创建 `.env.example` 文件，统一管理以下变量：

- `ALIBABA_CLOUD_API_KEY`
- `MONGODB_ATLAS_URI`
- `DASHVECTOR_ENDPOINT`
- `LOCAL_PYTHON_PORT` (本地算法通讯端口)